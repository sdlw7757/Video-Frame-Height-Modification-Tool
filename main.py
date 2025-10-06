#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频帧高度修改工具
支持3840x2160和5120x2880分辨率转换，使用GPU加速
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
import sys
from pathlib import Path
from video_processor import VideoProcessor
import queue
import time

# 添加FFmpeg到临时环境变量
def setup_ffmpeg_environment():
    """设置FFmpeg环境变量"""
    # 获取程序所在目录
    if getattr(sys, 'frozen', False):
        # 如果是打包后的exe文件
        current_dir = Path(sys.executable).parent
    else:
        # 如果是Python脚本
        current_dir = Path(__file__).parent
    
    # FFmpeg可执行文件路径
    ffmpeg_bin_dir = current_dir / "bin"
    
    if ffmpeg_bin_dir.exists():
        # 获取当前PATH环境变量
        current_path = os.environ.get('PATH', '')
        ffmpeg_path_str = str(ffmpeg_bin_dir)
        
        # 检查是否已经在PATH中
        if ffmpeg_path_str not in current_path:
            # 将FFmpeg路径添加到PATH开头（最高优先级）
            new_path = ffmpeg_path_str + os.pathsep + current_path
            os.environ['PATH'] = new_path
            print(f"✓ 已添加FFmpeg到环境变量: {ffmpeg_path_str}")
        else:
            print(f"✓ FFmpeg路径已存在于环境变量中")
        
        # 验证FFmpeg是否可用
        ffmpeg_exe = ffmpeg_bin_dir / "ffmpeg.exe"
        ffprobe_exe = ffmpeg_bin_dir / "ffprobe.exe"
        
        if ffmpeg_exe.exists() and ffprobe_exe.exists():
            print(f"✓ FFmpeg工具验证成功")
            return True
        else:
            print(f"⚠ 警告: FFmpeg工具文件不完整")
            return False
    else:
        print(f"⚠ 警告: 找不到FFmpeg工具目录: {ffmpeg_bin_dir}")
        return False

class VideoResizeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("视频帧高度修改工具")
        self.root.geometry("800x700")
        self.root.resizable(True, True)
        
        # 设置应用图标（如果有的话）
        try:
            self.root.iconbitmap("icon.ico")
        except:
            pass
        
        # 在初始化视频处理器之前设置FFmpeg环境
        ffmpeg_ready = setup_ffmpeg_environment()
        if not ffmpeg_ready:
            messagebox.showwarning(
                "环境警告", 
                "FFmpeg工具设置不完整，可能影响程序功能。\n\n"
                "请确保以下文件存在：\n"
                "- bin/ffmpeg.exe\n"
                "- bin/ffprobe.exe"
            )
        
        # 初始化视频处理器
        self.video_processor = VideoProcessor()
        
        # 消息队列用于线程间通信
        self.message_queue = queue.Queue()
        
        # 当前选择的文件
        self.selected_files = []
        
        # 创建界面
        self.create_widgets()
        
        # 启动消息队列监听
        self.check_queue()
        
    def create_widgets(self):
        """创建GUI界面"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # 标题
        title_label = ttk.Label(main_frame, text="视频帧高度修改工具", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # 文件选择区域
        file_frame = ttk.LabelFrame(main_frame, text="文件选择", padding="10")
        file_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        file_frame.columnconfigure(1, weight=1)
        
        # 选择文件按钮
        select_btn = ttk.Button(file_frame, text="选择视频文件", 
                               command=self.select_files)
        select_btn.grid(row=0, column=0, padx=(0, 10))
        
        # 文件列表
        self.file_listbox = tk.Listbox(file_frame, height=4)
        self.file_listbox.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        
        # 滚动条
        file_scrollbar = ttk.Scrollbar(file_frame, orient="vertical", 
                                      command=self.file_listbox.yview)
        file_scrollbar.grid(row=0, column=2, sticky="ns")
        self.file_listbox.config(yscrollcommand=file_scrollbar.set)
        
        # 清空按钮
        clear_btn = ttk.Button(file_frame, text="清空", 
                              command=self.clear_files)
        clear_btn.grid(row=0, column=3)
        
        # 转换设置区域
        settings_frame = ttk.LabelFrame(main_frame, text="转换设置", padding="10")
        settings_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        
        # GPU加速选项 - 强制默认启用
        self.gpu_var = tk.BooleanVar()
        self.gpu_var.set(True)  # 明确设置为True
        gpu_check = ttk.Checkbutton(settings_frame, text="启用GPU加速（推荐）", 
                                variable=self.gpu_var)
        gpu_check.grid(row=0, column=0, sticky=tk.W)
        gpu_check.state(['!alternate'])  # 确保不是不确定状态
        gpu_check.state(['selected'])    # 强制选中状态
        
        # GPU状态显示
        self.gpu_status_var = tk.StringVar(value="")
        gpu_status_label = ttk.Label(settings_frame, textvariable=self.gpu_status_var, 
                                    font=("Arial", 8), foreground="green")
        gpu_status_label.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        
        # 初始化时显示GPU状态
        gpu_options = self.video_processor.detect_gpu()
        if gpu_options:
            self.gpu_status_var.set(f"✓ 检测到: {', '.join(gpu_options[:2])}")
        else:
            self.gpu_status_var.set("⚠ 未检测到GPU")
        
        # 覆盖原文件选项
        self.overwrite_var = tk.BooleanVar(value=False)
        overwrite_check = ttk.Checkbutton(settings_frame, text="覆盖原文件", 
                                      variable=self.overwrite_var)
        overwrite_check.grid(row=1, column=0, sticky=tk.W)
        
        # 转换规则说明
        rules_frame = ttk.LabelFrame(main_frame, text="转换规则", padding="10")
        rules_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        
        rules_text = """转换规则：
• 检测到宽度为 3840 的视频 → 转换为 3840 x 2160 (4K)
• 检测到宽度为 5120 的视频 → 转换为 5120 x 2880 (5K)
• 检测到宽度为 7680 的视频 → 转换为 7680 x 4320 (8K)
• 其他分辨率的视频将被跳过

注意：转换后的视频将保存在原视频同目录下，文件名添加 '_resized' 后缀"""
        
        rules_label = ttk.Label(rules_frame, text=rules_text, justify=tk.LEFT)
        rules_label.grid(row=0, column=0, sticky=tk.W)
        
        # 操作按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=3, pady=(0, 10))
        
        self.start_btn = ttk.Button(button_frame, text="开始转换", 
                                   command=self.start_conversion, 
                                   style="Accent.TButton")
        self.start_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.stop_btn = ttk.Button(button_frame, text="停止转换", 
                                  command=self.stop_conversion, 
                                  state="disabled")
        self.stop_btn.pack(side=tk.LEFT)
        
        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, 
                                           maximum=100)
        self.progress_bar.grid(row=5, column=0, columnspan=3, sticky="ew", 
                              pady=(0, 5))
        
        # 进度详情标签
        self.progress_detail_var = tk.StringVar(value="")
        progress_detail_label = ttk.Label(main_frame, textvariable=self.progress_detail_var, 
                                         font=("Arial", 8), foreground="gray")
        progress_detail_label.grid(row=6, column=0, columnspan=3, sticky=tk.W)
        
        # 状态标签
        self.status_var = tk.StringVar(value="就绪")
        status_label = ttk.Label(main_frame, textvariable=self.status_var)
        status_label.grid(row=7, column=0, columnspan=3, sticky=tk.W)
        
        # 日志区域
        log_frame = ttk.LabelFrame(main_frame, text="转换日志", padding="10")
        log_frame.grid(row=8, column=0, columnspan=3, sticky="nsew", 
                       pady=(10, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(8, weight=1)
        
        # 日志文本框
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, 
                                                  wrap=tk.WORD, 
                                                  font=("Consolas", 9))
        self.log_text.grid(row=0, column=0, sticky="nsew")
        
        # 日志按钮
        log_btn_frame = ttk.Frame(log_frame)
        log_btn_frame.grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        
        clear_log_btn = ttk.Button(log_btn_frame, text="清空日志", 
                                  command=self.clear_log)
        clear_log_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        copy_log_btn = ttk.Button(log_btn_frame, text="复制日志", 
                                 command=self.copy_log)
        copy_log_btn.pack(side=tk.LEFT)
        
    def select_files(self):
        """选择视频文件"""
        filetypes = [
            ("视频文件", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.m4v *.3gp"),
            ("所有文件", "*.*")
        ]
        
        files = filedialog.askopenfilenames(
            title="选择视频文件",
            filetypes=filetypes
        )
        
        if files:
            self.selected_files.extend(files)
            self.update_file_list()
            
    def clear_files(self):
        """清空文件列表"""
        self.selected_files.clear()
        self.update_file_list()
        
    def update_file_list(self):
        """更新文件列表显示"""
        self.file_listbox.delete(0, tk.END)
        for file_path in self.selected_files:
            filename = os.path.basename(file_path)
            self.file_listbox.insert(tk.END, filename)
            
    def start_conversion(self):
        """开始转换"""
        if not self.selected_files:
            messagebox.showwarning("警告", "请先选择视频文件！")
            return
            
        # 禁用开始按钮，启用停止按钮
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        
        # 重置进度条
        self.progress_var.set(0)
        
        # 清空之前的日志
        self.clear_log()
        
        # 显示GPU设置状态
        gpu_enabled = self.gpu_var.get()
        gpu_options = self.video_processor.detect_gpu()
        gpu_status = "启用" if gpu_enabled else "禁用"
        self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] ==> GPU加速设置: {gpu_status}\n")
        if gpu_enabled and gpu_options:
            self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] ==> 可用GPU: {', '.join(gpu_options)}\n")
        self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] ==> 开始处理 {len(self.selected_files)} 个文件\n\n")
        
        # 在新线程中进行转换
        self.conversion_thread = threading.Thread(
            target=self.conversion_worker,
            daemon=True
        )
        self.conversion_thread.start()
        
    def stop_conversion(self):
        """停止转换"""
        self.video_processor.stop_conversion()
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.status_var.set("转换已停止")
        
    def conversion_worker(self):
        """转换工作线程"""
        try:
            total_files = len(self.selected_files)
            for i, file_path in enumerate(self.selected_files):
                if self.video_processor.should_stop:
                    break
                    
                # 更新状态
                filename = os.path.basename(file_path)
                self.message_queue.put(("status", f"正在处理: {filename}"))
                self.message_queue.put(("log", f"开始处理文件: {filename}"))
                
                # 获取视频信息
                video_info = self.video_processor.get_video_info(file_path)
                if not video_info:
                    self.message_queue.put(("log", f"错误: 无法获取视频信息 - {filename}"))
                    continue
                    
                width = video_info.get('width', 0)
                height = video_info.get('height', 0)
                duration = video_info.get('duration', 0)
                
                self.message_queue.put(("log", f"视频分辨率: {width}x{height}"))
                if duration > 0:
                    duration_str = f"{int(duration//3600):02d}:{int((duration%3600)//60):02d}:{int(duration%60):02d}"
                    self.message_queue.put(("log", f"视频时长: {duration_str}"))
                
                # 检查是否需要转换
                if width == 3840:
                    target_height = 2160
                elif width == 5120:
                    target_height = 2880
                elif width == 7680:
                    target_height = 4320
                else:
                    self.message_queue.put(("log", f"跳过文件 (不支持的宽度): {filename}"))
                    continue
                    
                # 如果高度已经正确，跳过
                if height == target_height:
                    self.message_queue.put(("log", f"跳过文件 (高度已正确): {filename}"))
                    continue
                    
                # 生成输出文件路径
                if self.overwrite_var.get():
                    output_path = file_path
                else:
                    file_dir = os.path.dirname(file_path)
                    file_name = os.path.splitext(os.path.basename(file_path))[0]
                    file_ext = os.path.splitext(file_path)[1]
                    output_path = os.path.join(file_dir, f"{file_name}_resized{file_ext}")
                
                # 执行转换前再次确认GPU设置
                gpu_enabled = self.gpu_var.get()
                gpu_status_text = "启用" if gpu_enabled else "禁用"
                self.message_queue.put(("log", f"转换参数 - GPU加速: {gpu_status_text}"))
                
                if not gpu_enabled:
                    # 如果GPU被禁用，提醒用户
                    self.message_queue.put(("log", "⚠️ 注意: 您已禁用GPU加速，转换速度将显著放慢"))
                    self.message_queue.put(("log", "提示: 可在转换设置中勾选'GPU加速'来提高性能"))
                
                self.message_queue.put(("log", f"开始转换到 {width}x{target_height}"))
                # 重置单个文件进度条
                self.message_queue.put(("file_progress", 0))
                # 设置当前处理的文件索引，用于混合进度计算
                self.message_queue.put(("current_file_info", (i, total_files)))
                
                success = self.video_processor.convert_video(
                    file_path, 
                    output_path, 
                    width, 
                    target_height,
                    self.gpu_var.get(),
                    self.message_queue
                )
                
                if success:
                    self.message_queue.put(("log", f"转换完成: {os.path.basename(output_path)}"))
                    self.message_queue.put(("file_progress", 100))  # 单个文件完成
                else:
                    self.message_queue.put(("log", f"转换失败: {filename}"))
                    
                # 更新总进度
                overall_progress = ((i + 1) / total_files) * 100
                self.message_queue.put(("progress", overall_progress))
                
            # 转换完成
            if not self.video_processor.should_stop:
                self.message_queue.put(("status", "转换完成"))
                self.message_queue.put(("log", "所有文件处理完成！"))
            else:
                self.message_queue.put(("status", "转换已停止"))
                
        except Exception as e:
            self.message_queue.put(("log", f"错误: {str(e)}"))
            self.message_queue.put(("status", "转换出错"))
        finally:
            self.message_queue.put(("enable_start", None))
            
    def check_queue(self):
        """检查消息队列"""
        try:
            while True:
                message_type, data = self.message_queue.get_nowait()
                
                if message_type == "status":
                    self.status_var.set(data)
                elif message_type == "log":
                    self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {data}\n")
                    self.log_text.see(tk.END)
                elif message_type == "progress":
                    # 总体进度（文件完成进度）
                    self.progress_var.set(data)
                elif message_type == "progress_percent":
                    # 单个文件的进度百分比（用于更精确的进度显示）
                    current_file_progress = data
                    self.progress_detail_var.set(f"当前文件进度: {current_file_progress:.1f}%")
                    
                    # 计算混合进度：结合文件完成进度和当前文件进度
                    if hasattr(self, 'current_file_index') and hasattr(self, 'total_files'):
                        if self.total_files > 0:
                            # 已完成文件的进度
                            completed_files_progress = (self.current_file_index / self.total_files) * 100
                            # 当前文件的进度贡献
                            current_file_contribution = (current_file_progress / 100) * (100 / self.total_files)
                            # 总进度
                            total_progress = completed_files_progress + current_file_contribution
                            self.progress_var.set(min(total_progress, 100))
                    
                elif message_type == "current_file_info":
                    # 设置当前文件信息
                    self.current_file_index, self.total_files = data
                elif message_type == "file_progress":
                    # 单个文件的进度
                    if data == 0:
                        self.progress_detail_var.set("开始转换...")
                    elif data == 100:
                        self.progress_detail_var.set("当前文件转换完成")
                elif message_type == "enable_start":
                    self.start_btn.config(state="normal")
                    self.stop_btn.config(state="disabled")
                    
        except queue.Empty:
            pass
        finally:
            # 每100ms检查一次队列
            self.root.after(100, self.check_queue)
            
    def clear_log(self):
        """清空日志"""
        self.log_text.delete(1.0, tk.END)
        
    def copy_log(self):
        """复制日志到剪贴板"""
        log_content = self.log_text.get(1.0, tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(log_content)
        messagebox.showinfo("提示", "日志已复制到剪贴板")


def main():
    """主函数"""
    # 初始化FFmpeg环境变量
    print("=== 视频帧高度修改工具 v1.0 ===")
    print("正在初始化FFmpeg环境...")
    
    ffmpeg_ready = setup_ffmpeg_environment()
    
    if ffmpeg_ready:
        print("✓ FFmpeg环境初始化成功")
    else:
        print("⚠ FFmpeg环境初始化警告")
    
    print("正在启动用户界面...")
    
    # 创建主窗口
    root = tk.Tk()
    app = VideoResizeApp(root)
    
    # 启动应用
    root.mainloop()


if __name__ == "__main__":
    main()