import os
import re
from mcdreforged.api.all import *

CONFIG_PATH = os.path.join('config', 'file_manager.json')

DEFAULT_CONFIG = {
    'allowed_players': [''],
    'max_preview_lines': 15,
    'items_per_page': 10,
    'protected_files': [
        'server.properties',
        'whitelist.json',
        'ops.json'
    ]
}

class FileManager:
    def __init__(self, server: PluginServerInterface):
        self.server = server
        self.config = DEFAULT_CONFIG.copy()
        self.browser_sessions = {}
        self.server_path = os.getcwd()
        self.load_config()
        
    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                self.config = self.server.load_config_simple(
                    CONFIG_PATH, DEFAULT_CONFIG, in_data_folder=False
                )
            except:
                self.server.logger.exception("Failed to load config, using defaults")
        else:
            self.server.save_config_simple(self.config, CONFIG_PATH, in_data_folder=False)
    
    def __get_full_path(self, path: str) -> str:
        full_path = os.path.abspath(os.path.join(self.server_path, path))
        if not full_path.startswith(self.server_path):
            raise PermissionError("访问服务器目录外的路径被禁止")
        return full_path
    
    def __check_permission(self, source: CommandSource) -> bool:
        if source.is_player:
            player = source.player
            return player in self.config['allowed_players'] or self.server.get_permission_level(player) >= 3
        else:
            return True
    
    def __is_protected(self, file_name: str) -> bool:
        return file_name in self.config['protected_files']
    
    def __get_player_session(self, player: str) -> dict:
        if player not in self.browser_sessions:
            self.browser_sessions[player] = {
                'path': '.',
                'page': 1
            }
        return self.browser_sessions[player]
    
    def __normalize_path(self, path: str) -> str:
        path = path.strip().strip("'").strip('"')
        path = path.replace("\\", "/")
        path = re.sub(r'/+', '/', path)
        if path != "/" and path.endswith("/"):
            path = path[:-1]
        return path
    
    def __list_directory(self, path: str) -> tuple:
        full_path = self.__get_full_path(path)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"路径不存在: {path}")
        if os.path.isfile(full_path):
            raise NotADirectoryError(f"路径是文件而非目录: {path}")
        dirs = []
        files = []
        for item in os.listdir(full_path):
            item_path = os.path.join(full_path, item)
            if os.path.isdir(item_path):
                dirs.append(item)
            else:
                files.append(item)
        dirs.sort(key=str.lower)
        files.sort(key=str.lower)
        return dirs, files
    
    def __format_path_arg(self, path: str) -> str:
        if ' ' in path:
            return f'"{path}"'
        return path
    
    def __get_line_range(self, content: str, start_line: int, max_lines: int, file_path: str) -> tuple:
        lines = content.splitlines()
        total_lines = len(lines)
        start_line = max(1, min(start_line, total_lines))
        end_line = min(start_line + max_lines - 1, total_lines)
        preview_lines = lines[start_line-1:end_line]
        preview_with_numbers = []
        for i, line in enumerate(preview_lines, start=start_line):
            line_number = RText(f"§7{i:4d}§f | ", styles=RStyle.underlined)
            line_number.set_hover_text(f"点击编辑第 {i} 行")
            line_number.set_click_event(RAction.suggest_command, f"!!fm edit '{file_path}' {i} ")
            line_content = RText(line)
            full_line = RTextList(line_number, line_content)
            preview_with_numbers.append(full_line)
        preview = RTextList()
        for line in preview_with_numbers:
            preview.append(line)
            preview.append('\n')
        return preview, start_line, end_line, total_lines
    
    def show_help(self, source: CommandSource):
        help_menu = RTextList(
            "§6===== 文件管理器帮助菜单 =====\n",
            "§a主要命令:\n",
            RText("  §e!!fm browse [路径] [页码]§7 - 浏览文件目录\n").h("点击输入").c(RAction.suggest_command, "!!fm browse "),
            RText("  §e!!fm view <文件路径> [起始行]§7 - 查看文件内容\n").h("点击输入").c(RAction.suggest_command, "!!fm view "),
            RText("  §e!!fm edit <文件路径> <行号> <内容>§7 - 编辑文件行\n").h("点击输入").c(RAction.suggest_command, "!!fm edit "),
            RText("  §e!!fm delete <文件路径>§7 - 删除文件\n").h("点击输入").c(RAction.suggest_command, "!!fm delete "),
            RText("  §e!!fm help§7 - 显示此帮助菜单\n").h("点击输入").c(RAction.suggest_command, "!!fm help"),
            "\n§a当前配置:\n",
            f"§7- 目前允许操作玩家: §e{', '.join(self.config['allowed_players'])}§7&OP\n",
            f"§7- 受保护文件: §e{', '.join(self.config['protected_files'])}\n",
            "\n§a小提示:\n",
            "§7- 路径包含空格时需用引号包裹\n",
        )
        source.reply(help_menu)
    
    def browse_directory(self, source: CommandSource, path: str = None, page: int = None):
        if not self.__check_permission(source):
            source.reply("§c你没有权限使用此命令")
            return
        player = source.player if source.is_player else "Console"
        session = self.__get_player_session(player)
        if path is not None:
            path = self.__normalize_path(path)
            session['path'] = path
            session['page'] = 1
        if page is not None:
            session['page'] = page
        current_path = session['path']
        current_page = session['page']
        try:
            dirs, files = self.__list_directory(current_path)
            all_items = dirs + files
            items_per_page = self.config['items_per_page']
            total_pages = max(1, (len(all_items) + items_per_page - 1) // items_per_page)
            if current_page < 1:
                current_page = 1
            elif current_page > total_pages:
                current_page = total_pages
            session['page'] = current_page
            start_idx = (current_page - 1) * items_per_page
            end_idx = start_idx + items_per_page
            page_items = all_items[start_idx:end_idx]
            response = RTextList()
            response.append(RText("§6===== 文件管理器 =====\n"))
            response.append(f"§7当前路径: §e{current_path}\n")
            response.append(f"§7总项目: §a{len(all_items)} §7| 当前页: §e{current_page}§7/§e{total_pages}\n")
            nav_buttons = RTextList()
            if current_page > 1:
                nav_buttons.append(
                    RText(" [◀前页] ").h("点击前往上一页").c(RAction.suggest_command, 
                        f"!!fm browse '{current_path}' {current_page-1}")
                )
            if current_page < total_pages:
                nav_buttons.append(
                    RText(" [后页▶] ").h("点击前往下一页").c(RAction.suggest_command, 
                        f"!!fm browse '{current_path}' {current_page+1}")
                )
            if nav_buttons:
                response.append(nav_buttons)
                response.append("\n")
            if current_path != '.':
                parent_path = os.path.dirname(current_path)
                if parent_path == '':
                    parent_path = '.'
                response.append(
                    RText("§b[..] §7(返回上级目录)\n").h("点击返回上级目录")
                    .c(RAction.suggest_command, f"!!fm browse '{parent_path}'")
                )
            for item in page_items:
                item_path = os.path.join(current_path, item)
                full_item_path = self.__get_full_path(item_path)
                if os.path.isdir(full_item_path):
                    response.append(
                        RText(f"§b[DIR] §3{item}\n").h("点击进入目录")
                        .c(RAction.suggest_command, f"!!fm browse '{item_path}'")
                    )
                else:
                    file_size = os.path.getsize(full_item_path)
                    size_str = f"§7({file_size}字节)" if file_size < 1024 else f"§7({file_size/1024:.1f}KB)"
                    response.append(
                        RText(f"§a[FILE] §f{item} {size_str}\n").h("点击查看文件")
                        .c(RAction.suggest_command, f"!!fm view '{item_path}'")
                    )
            response.append("\n§6操作:\n")
            response.append(
                RText(" [刷新] ").h("点击刷新当前目录").c(RAction.suggest_command, 
                    f"!!fm browse '{current_path}'")
            )
            response.append(
                RText(" [根目录] ").h("返回根目录").c(RAction.suggest_command, "!!fm browse .")
            )
            response.append(
                RText(" [帮助] ").h("查看帮助菜单").c(RAction.suggest_command, "!!fm help")
            )
            source.reply(response)
        except Exception as e:
            source.reply(f"§c错误: {str(e)}")
            self.server.logger.error(f"文件浏览错误: {str(e)}")
    
    def view_file(self, source: CommandSource, file_path: str, start_line: int = 1):
        if not self.__check_permission(source):
            source.reply("§c你没有权限使用此命令")
            return
        file_path = self.__normalize_path(file_path)
        try:
            full_path = self.__get_full_path(file_path)
            if not os.path.exists(full_path):
                source.reply(f"§c文件不存在: {file_path}")
                return
            if not os.path.isfile(full_path):
                source.reply(f"§c路径不是文件: {file_path}")
                return
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            max_lines = self.config['max_preview_lines']
            preview, start_line, end_line, total_lines = self.__get_line_range(
                content, start_line, max_lines, file_path)
            file_size = os.path.getsize(full_path)
            response = RTextList()
            response.append(RText("§6===== 文件查看 =====\n"))
            response.append(f"§7路径: §e{file_path}\n")
            response.append(f"§7大小: §a{file_size} 字节\n")
            response.append(f"§7行数: §a{total_lines} 行\n")
            response.append(f"§7显示行: §e{start_line}-{end_line}§7/§a{total_lines}\n")
            response.append("\n§6内容预览:\n")
            response.append(preview)
            nav_buttons = RTextList()
            if start_line > 1:
                prev_start = max(1, start_line - max_lines)
                nav_buttons.append(
                    RText(" [◀前页] ").h("查看前几行").c(RAction.suggest_command, 
                        f"!!fm view '{file_path}' {prev_start}")
                )
            if end_line < total_lines:
                next_start = start_line + max_lines
                nav_buttons.append(
                    RText(" [后页▶] ").h("查看后几行").c(RAction.suggest_command, 
                        f"!!fm view '{file_path}' {next_start}")
                )
            if nav_buttons:
                response.append("\n")
                response.append(nav_buttons)
            response.append("\n\n§6操作:\n")
            response.append(
                RText(" [编辑文件] ").h("编辑整个文件").c(RAction.suggest_command, 
                    f"!!fm edit '{file_path}' ")
            )
            response.append(
                RText(" [删除] ").h("点击删除此文件").c(RAction.suggest_command, 
                    f"!!fm delete '{file_path}'")
            )
            response.append(
                RText(" [返回] ").h("返回文件浏览器").c(RAction.suggest_command, "!!fm browse")
            )
            response.append(
                RText(" [帮助] ").h("查看帮助菜单").c(RAction.suggest_command, "!!fm help")
            )
            source.reply(response)
        except Exception as e:
            source.reply(f"§c错误: {str(e)}")
            self.server.logger.error(f"查看文件错误: {str(e)}")
    
    def edit_line(self, source: CommandSource, file_path: str, line_number: int, new_content: str):
        if not self.__check_permission(source):
            source.reply("§c你没有权限使用此命令")
            return
        try:
            line_number = int(line_number)
            if line_number < 1:
                source.reply("§c行号必须大于0")
                return
        except ValueError:
            source.reply("§c无效的行号")
            return
        file_path = self.__normalize_path(file_path)
        try:
            full_path = self.__get_full_path(file_path)
            if self.__is_protected(os.path.basename(full_path)):
                source.reply(f"§c此文件受保护，无法修改: {file_path}")
                return
            if os.path.isdir(full_path):
                source.reply(f"§c无法修改目录: {file_path}")
                return
            if not os.path.exists(full_path):
                open(full_path, 'w').close()
                source.reply(f"§a创建新文件: {file_path}")
            with open(full_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            lines = [line.rstrip('\n') for line in lines]
            if line_number <= len(lines):
                old_content = lines[line_number - 1]
                lines[line_number - 1] = new_content
                operation = "替换"
            else:
                while len(lines) < line_number - 1:
                    lines.append("")
                lines.append(new_content)
                operation = "添加"
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            total_lines = len(lines)
            response = RTextList()
            response.append(RText(f"§a行编辑成功! ({operation})\n"))
            response.append(f"§7文件: §e{os.path.basename(file_path)}\n")
            response.append(f"§7行号: §a{line_number}\n")
            if operation == "替换":
                response.append(f"§7原内容: §c{old_content}\n")
            response.append(f"§7新内容: §a{new_content}\n")
            response.append(f"§7总行数: §a{total_lines} 行\n")
            response.append("\n§6操作:\n")
            response.append(
                RText(" [查看] ").h("查看文件内容").c(RAction.suggest_command, 
                    f"!!fm view '{file_path}'")
            )
            response.append(
                RText(" [继续编辑] ").h("编辑其他行").c(RAction.suggest_command, 
                    f"!!fm edit '{file_path}' ")
            )
            response.append(
                RText(" [浏览] ").h("返回文件浏览器").c(RAction.suggest_command, "!!fm browse")
            )
            response.append(
                RText(" [帮助] ").h("查看帮助菜单").c(RAction.suggest_command, "!!fm help")
            )
            source.reply(response)
        except Exception as e:
            source.reply(f"§c编辑行时出错: {str(e)}")
            self.server.logger.error(f"编辑行错误: {str(e)}")
    
    def delete_file(self, source: CommandSource, file_path: str):
        if not self.__check_permission(source):
            source.reply("§c你没有权限使用此命令")
            return
        file_path = self.__normalize_path(file_path)
        try:
            full_path = self.__get_full_path(file_path)
            if not os.path.exists(full_path):
                source.reply(f"§c文件不存在: {file_path}")
                return
            if self.__is_protected(os.path.basename(full_path)):
                source.reply(f"§c此文件受保护，无法删除: {file_path}")
                return
            if os.path.isdir(full_path):
                source.reply(f"§c无法删除目录: {file_path}")
                return
            os.remove(full_path)
            response = RTextList()
            response.append(RText("§a文件删除成功!\n"))
            response.append(f"§7已删除: §e{file_path}\n")
            response.append("\n§6操作:\n")
            response.append(
                RText(" [浏览] ").h("返回文件浏览器").c(RAction.suggest_command, "!!fm browse")
            )
            response.append(
                RText(" [帮助] ").h("查看帮助菜单").c(RAction.suggest_command, "!!fm help")
            )
            source.reply(response)
        except Exception as e:
            source.reply(f"§c错误: {str(e)}")
            self.server.logger.error(f"删除文件错误: {str(e)}")

def on_load(server: PluginServerInterface, old_module):
    global fm
    fm = FileManager(server)
    server.register_help_message('!!fm', '交互式文件管理器')
    def create_browse_command():
        cmd = Literal('browse').runs(lambda src: fm.browse_directory(src))
        cmd = cmd.then(
            QuotableText('path').then(
                Integer('page').runs(
                    lambda src, ctx: fm.browse_directory(src, ctx['path'], ctx['page'])
                )
            ).runs(
                lambda src, ctx: fm.browse_directory(src, ctx['path'])
            )
        )
        return cmd
    view_command = Literal('view').then(
        QuotableText('file_path').then(
            Integer('start_line').runs(
                lambda src, ctx: fm.view_file(src, ctx['file_path'], ctx['start_line'])
            )
        ).runs(
            lambda src, ctx: fm.view_file(src, ctx['file_path'])
        )
    )
    edit_command = Literal('edit').then(
        QuotableText('file_path').then(
            Integer('line').then(
                GreedyText('content').runs(lambda src, ctx: fm.edit_line(src, ctx['file_path'], ctx['line'], ctx['content']))
            )
        )
    )
    delete_command = Literal('delete').then(
        QuotableText('file_path').runs(lambda src, ctx: fm.delete_file(src, ctx['file_path']))
    )
    help_command = Literal('help').runs(lambda src: fm.show_help(src))
    root_command = Literal('!!fm').runs(lambda src: fm.show_help(src))
    root_command = root_command.then(create_browse_command())
    root_command = root_command.then(view_command)
    root_command = root_command.then(edit_command)
    root_command = root_command.then(delete_command)
    root_command = root_command.then(help_command)
    server.register_command(root_command)
    server.logger.info('文件管理器已加载')
    server.logger.info('使用 !!fm 查看帮助菜单')

def on_unload(server: PluginServerInterface):
    server.logger.info('文件管理器已卸载')