#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频处理器模块
负责FFmpeg调用和GPU加速视频转换
"""

import os
import subprocess
import json
import re
import time


class VideoProcessor:
    def __init__(self):
        # 获取FFmpeg和FFprobe路径
        base_dir = os.path.dirname(__file__)
        self.ffmpeg_path = os.path.join(base_dir, "bin", "ffmpeg.exe")
        self.ffprobe_path = os.path.join(base_dir, "bin", "ffprobe.exe")
        
        # 停止标志
        self.should_stop = False
        
        # 当前进程
        self.current_process = None
        
    def get_video_info(self, video_path):
        """获取视频信息"""
        result = None
        try:
            # 使用引号包裹路径避免特殊字符问题
            cmd = [
                self.ffprobe_path,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                video_path
            ]
            
            # 使用shell=False并添加超时控制
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=60,  # 60秒超时
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode != 0:
                # 打印错误信息用于调试
                error_msg = result.stderr.strip() if result.stderr else '未知错误'
                print(f"FFprobe错误 (exit code {result.returncode}): {error_msg}")
                print(f"文件路径: {video_path}")
                return None
                
            if not result.stdout.strip():
                print(f"FFprobe返回了空结果: {video_path}")
                return None
                
            data = json.loads(result.stdout)
            
            # 查找视频流
            video_stream = None
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break
                    
            if not video_stream:
                print(f"未找到视频流: {video_path}")
                return None
                
            width = video_stream.get('width')
            height = video_stream.get('height')
            
            if not width or not height:
                print(f"视频分辨率信息缺失: {video_path}")
                return None
                
            return {
                'width': int(width),
                'height': int(height),
                'duration': float(data.get('format', {}).get('duration', 0)),
                'bitrate': int(data.get('format', {}).get('bit_rate', 0)) if data.get('format', {}).get('bit_rate') else 0,
                'codec': video_stream.get('codec_name', ''),
                'fps': self._parse_fps(video_stream.get('r_frame_rate', ''))
            }
            
        except subprocess.TimeoutExpired:
            print(f"FFprobe超时 (60秒): {video_path}")
            return None
        except json.JSONDecodeError as e:
            print(f"JSON解析错误: {e}")
            if result and result.stdout:
                print(f"FFprobe输出: {result.stdout[:200]}")
            return None
        except Exception as e:
            print(f"获取视频信息出错: {e}")
            print(f"文件路径: {video_path}")
            return None
            
    def _parse_fps(self, fps_str):
        """解析帧率字符串"""
        try:
            if '/' in fps_str:
                num, den = fps_str.split('/')
                return float(num) / float(den)
            else:
                return float(fps_str)
        except:
            return 30.0  # 默认帧率
            
    def detect_gpu(self):
        """检测可用的GPU加速选项"""
        gpu_options = []
        
        # 检测NVIDIA GPU (NVENC)
        try:
            cmd = [self.ffmpeg_path, "-hide_banner", "-encoders"]
            result = subprocess.run(cmd, capture_output=True, text=True,
                                  creationflags=subprocess.CREATE_NO_WINDOW,
                                  timeout=10)
            
            encoders_output = result.stdout
            
            # 检测各种GPU编码器
            if "h264_nvenc" in encoders_output:
                gpu_options.append("nvenc")
                # 检测是否支持高分辨率
                if "hevc_nvenc" in encoders_output:  # HEVC通常支持更高分辨率
                    gpu_options.append("nvenc_hevc")
                    
            if "h264_amf" in encoders_output:  # AMD GPU
                gpu_options.append("amf")
                
            if "h264_qsv" in encoders_output:  # Intel QuickSync
                gpu_options.append("qsv")
                
        except Exception as e:
            print(f"GPU检测出错: {e}")
            
        return gpu_options
        
    def _check_gpu_resolution_support(self, width, height, gpu_type):
        """检测GPU是否支持指定分辨率"""
        # 放宽分辨率限制，现代GPU通常支持更高分辨率
        
        # NVIDIA NVENC分辨率限制（基于实际测试结果）
        if gpu_type == "nvenc":
            # 基于测试：5K及以上分辨率NVENC不稳定
            max_width = 4096   # 限制在4K+
            max_height = 2304  # 略高于4K
            if width > max_width or height > max_height:
                return False, f"NVENC在高分辨率下不稳定 {width}x{height}（建议限制: {max_width}x{max_height}）"
                
        # AMD AMF分辨率限制
        elif gpu_type == "amf":
            max_width = 7680   # 支持到8K
            max_height = 4320  # 8K高度
            if width > max_width or height > max_height:
                return False, f"AMD AMF可能不支持 {width}x{height} 分辨率（限制: {max_width}x{max_height}）"
                
        # Intel QuickSync分辨率限制
        elif gpu_type == "qsv":
            max_width = 7680   # 支持到8K
            max_height = 4320  # 8K高度
            if width > max_width or height > max_height:
                return False, f"Intel QSV可能不支持 {width}x{height} 分辨率（限制: {max_width}x{max_height}）"
                
        return True, ""
        
    def convert_video(self, input_path, output_path, target_width, target_height, 
                     use_gpu=True, message_queue=None):
        """转换视频 - 支持GPU失败时自动回退到CPU"""
        # 首先尝试GPU编码（如果启用）
        if use_gpu:
            success = self._execute_ffmpeg(input_path, output_path, target_width, target_height, True, message_queue)
            if success:
                return True
            
            # GPU失败，回退到CPU
            if message_queue:
                message_queue.put(("log", "GPU编码失败，自动切换到CPU编码..."))
        
        # 使用CPU编码
        return self._execute_ffmpeg(input_path, output_path, target_width, target_height, False, message_queue)
    
    def _execute_ffmpeg(self, input_path, output_path, target_width, target_height, use_gpu, message_queue):
        """执行FFmpeg转换"""
        try:
            self.should_stop = False
            
            # 首先获取视频时长用于计算进度
            video_info = self.get_video_info(input_path)
            total_duration = video_info.get('duration', 0) if video_info else 0
            
            # 构建FFmpeg命令
            cmd = [self.ffmpeg_path]
            
            # 通用参数
            cmd.extend(["-hide_banner", "-loglevel", "error", "-stats"])
            
            # 输入文件
            cmd.extend(["-i", input_path])
            
            # 编码器设置
            if use_gpu:
                gpu_options = self.detect_gpu()
                # 根据分辨率选择合适的GPU编码参数
                is_high_res = target_width >= 5120  # 5K及以上分辨率
                gpu_used = False
                
                # 尝试NVIDIA NVENC
                if "nvenc" in gpu_options:
                    supported, msg = self._check_gpu_resolution_support(target_width, target_height, "nvenc")
                    if supported:
                        # 使用经过测试的最稳定参数
                        cmd.extend([
                            "-c:v", "h264_nvenc",
                            "-preset", "fast",      # fast预设最稳定
                            "-b:v", "5M"           # 简单的码率控制
                        ])
                        gpu_used = True
                        if message_queue:
                            message_queue.put(("log", "GPU加速: 使用 NVIDIA NVENC"))
                    else:
                        if message_queue:
                            message_queue.put(("log", f"NVENC限制: {msg}"))
                
                # 如果NVENC不可用，尝试AMD AMF
                if not gpu_used and "amf" in gpu_options:
                    supported, msg = self._check_gpu_resolution_support(target_width, target_height, "amf")
                    if supported:
                        if is_high_res:
                            cmd.extend([
                                "-c:v", "h264_amf",
                                "-quality", "balanced",  # 使用balanced而不是quality
                                "-rc", "vbr",
                                "-b:v", "12M",  # 降低码率
                                "-maxrate", "18M",
                                "-usage", "transcoding"  # 转码模式
                            ])
                        else:
                            cmd.extend([
                                "-c:v", "h264_amf",
                                "-quality", "quality",
                                "-rc", "vbr",
                                "-b:v", "8M"
                            ])
                        gpu_used = True
                        if message_queue:
                            message_queue.put(("log", "GPU加速: 使用 AMD AMF"))
                    else:
                        if message_queue:
                            message_queue.put(("log", f"AMD AMF限制: {msg}"))
                
                # 如果前面都不可用，尝试Intel QuickSync
                if not gpu_used and "qsv" in gpu_options:
                    supported, msg = self._check_gpu_resolution_support(target_width, target_height, "qsv")
                    if supported:
                        if is_high_res:
                            cmd.extend([
                                "-c:v", "h264_qsv",
                                "-preset", "medium",  # 使用medium而不是slower
                                "-profile:v", "main", # 使用main而不是high
                                "-b:v", "12M",       # 降低码率
                                "-maxrate", "18M",
                                "-bufsize", "24M"
                            ])
                        else:
                            cmd.extend([
                                "-c:v", "h264_qsv",
                                "-preset", "medium",
                                "-b:v", "8M"
                            ])
                        gpu_used = True
                        if message_queue:
                            message_queue.put(("log", "GPU加速: 使用 Intel QuickSync"))
                    else:
                        if message_queue:
                            message_queue.put(("log", f"Intel QSV限制: {msg}"))
                
                # 如果所有GPU都不可用，使用CPU
                if not gpu_used:
                    if message_queue:
                        message_queue.put(("log", "GPU不支持当前分辨率，使用CPU编码"))
                    # 根据分辨率选择CPU参数
                    if is_high_res:
                        cmd.extend([
                            "-c:v", "libx264",
                            "-preset", "ultrafast",  # 使用最快速度
                            "-crf", "28"            # 降低质量，提高速度
                        ])
                    else:
                        cmd.extend([
                            "-c:v", "libx264",
                            "-preset", "fast",
                            "-crf", "26"
                        ])
            else:
                # CPU编码
                is_high_res = target_width >= 5120
                if message_queue:
                    message_queue.put(("log", "GPU加速已禁用，使用CPU编码"))
                if is_high_res:
                    cmd.extend([
                        "-c:v", "libx264",
                        "-preset", "ultrafast",  # 使用最快速度
                        "-crf", "28"            # 降低质量，提高速度
                    ])
                else:
                    cmd.extend([
                        "-c:v", "libx264",
                        "-preset", "fast",
                        "-crf", "26"
                    ])
            
            # 添加分辨率和性能优化参数（对所有编码器）
            is_high_res = target_width >= 5120
            if is_high_res:
                # 高分辨率优化
                cmd.extend([
                    "-threads", "0",  # 使用所有可用线程
                    "-thread_type", "frame",  # 帧级多线程
                ])
                if message_queue:
                    message_queue.put(("log", f"检测到高分辨率 ({target_width}x{target_height})，使用优化的编码参数"))
            
            # 视频滤镜：调整分辨率（对所有编码器）
            cmd.extend([
                "-vf", f"scale={target_width}:{target_height}:flags=lanczos",  # 使用高质量缩放算法
                "-c:a", "copy",  # 音频流复制
                "-movflags", "+faststart",  # 优化文件结构
                "-y",  # 覆盖输出文件
                output_path
            ])
            
            if message_queue:
                cmd_str = " ".join([f'"{arg}"' if " " in arg else arg for arg in cmd])
                message_queue.put(("log", f"执行命令: {cmd_str}"))
                # 添加GPU使用情况的日志
                if use_gpu:
                    if "nvenc" in cmd_str:
                        message_queue.put(("log", "✓ 使用NVIDIA GPU加速 (NVENC)"))
                    elif "amf" in cmd_str:
                        message_queue.put(("log", "✓ 使用AMD GPU加速 (AMF)"))
                    elif "qsv" in cmd_str:
                        message_queue.put(("log", "✓ 使用Intel GPU加速 (QuickSync)"))
                    elif "libx264" in cmd_str:
                        message_queue.put(("log", "⚠ GPU不可用，回退到CPU编码 (libx264)"))
                else:
                    message_queue.put(("log", "使用CPU编码 (libx264)"))
                
            # 创建进程
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            # 监控进程输出
            while True:
                if self.should_stop:
                    self.current_process.terminate()
                    return False
                    
                # 同时读取stderr和stdout
                output = None
                if self.current_process.stderr is not None:
                    output = self.current_process.stderr.readline()
                if not output and self.current_process.stdout is not None:
                    output = self.current_process.stdout.readline()
                    
                if output == '' and self.current_process.poll() is not None:
                    break
                    
                if output and message_queue:
                    output_line = output.strip()
                    # 解析FFmpeg输出中的进度信息
                    if "time=" in output_line:
                        progress_info, progress_percent = self._parse_progress(output_line, total_duration)
                        if progress_info:
                            message_queue.put(("log", f"转换进度: {progress_info}"))
                        # 发送进度百分比
                        if progress_percent > 0:
                            message_queue.put(("progress_percent", progress_percent))
                    elif "frame=" in output_line:
                        # 处理帧数信息
                        progress_info, progress_percent = self._parse_progress(output_line, total_duration)
                        if progress_info:
                            message_queue.put(("log", f"转换进度: {progress_info}"))
                        # 即使没有时间信息，也可以通过帧数估算进度
                        if progress_percent > 0:
                            message_queue.put(("progress_percent", progress_percent))
                    elif "error" in output_line.lower() or "failed" in output_line.lower():
                        message_queue.put(("log", f"FFmpeg: {output_line}"))
                    # 在调试模式下显示所有输出
                    elif output_line and ("fps=" in output_line or "bitrate=" in output_line):
                        # 这是FFmpeg的统计信息行，包含进度信息
                        progress_info, progress_percent = self._parse_progress(output_line, total_duration)
                        if progress_percent > 0:
                            message_queue.put(("progress_percent", progress_percent))
                        
            # 检查返回码
            return_code = self.current_process.poll()
            if return_code == 0:
                return True
            else:
                if message_queue:
                    message_queue.put(("log", f"FFmpeg退出码: {return_code}"))
                return False
                
        except Exception as e:
            if message_queue:
                message_queue.put(("log", f"转换出错: {str(e)}"))
            return False
        finally:
            self.current_process = None
            
    def _parse_progress(self, output, total_duration=0):
        """解析FFmpeg进度输出"""
        try:
            # 处理progress格式的输出 (out_time_ms=xxxxx)
            time_ms_match = re.search(r'out_time_ms=(\d+)', output)
            if time_ms_match:
                current_ms = int(time_ms_match.group(1))
                current_seconds = current_ms / 1000000  # 微秒转秒
                
                # 计算百分比
                progress_percent = 0
                if total_duration > 0:
                    progress_percent = min((current_seconds / total_duration) * 100, 100)
                
                hours = int(current_seconds // 3600)
                minutes = int((current_seconds % 3600) // 60)
                seconds = current_seconds % 60
                
                return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}", progress_percent
            
            # 处理传统格式的时间输出 (time=xx:xx:xx.xx)
            time_match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', output)
            if time_match:
                hours = int(time_match.group(1))
                minutes = int(time_match.group(2))
                seconds = float(time_match.group(3))
                current_seconds = hours * 3600 + minutes * 60 + seconds
                
                # 计算百分比
                progress_percent = 0
                if total_duration > 0:
                    progress_percent = min((current_seconds / total_duration) * 100, 100)
                
                return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}", progress_percent
                
            # 查找帧数信息
            frame_match = re.search(r'frame=\s*(\d+)', output)
            if frame_match:
                frame_count = int(frame_match.group(1))
                return f"已处理 {frame_count} 帧", 0
                
        except Exception as e:
            print(f"进度解析错误: {e}")
            
        return None, 0
        
    def stop_conversion(self):
        """停止转换"""
        self.should_stop = True
        if self.current_process:
            try:
                self.current_process.terminate()
                # 等待进程结束
                for _ in range(10):  # 最多等待1秒
                    if self.current_process.poll() is not None:
                        break
                    time.sleep(0.1)
                
                # 如果进程仍然存在，强制终止
                if self.current_process.poll() is None:
                    self.current_process.kill()
            except:
                pass
                
    def get_supported_formats(self):
        """获取支持的视频格式"""
        try:
            cmd = [self.ffmpeg_path, "-formats"]
            result = subprocess.run(cmd, capture_output=True, text=True,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            
            formats = []
            lines = result.stdout.split('\n')
            
            for line in lines:
                if 'E ' in line and ('mp4' in line or 'avi' in line or 'mkv' in line):
                    formats.append(line.strip())
                    
            return formats
            
        except:
            return []


# 测试函数
def test_video_processor():
    """测试视频处理器"""
    processor = VideoProcessor()
    
    print("检测GPU加速选项:")
    gpu_options = processor.detect_gpu()
    print(f"可用GPU: {gpu_options}")
    
    print("\n支持的格式:")
    formats = processor.get_supported_formats()
    for fmt in formats[:10]:  # 只显示前10个
        print(f"  {fmt}")
        

if __name__ == "__main__":
    test_video_processor()