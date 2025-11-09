# dashscope SDK 版本需不低于 1.23.9
import os
import base64
import signal
import sys
import pyaudio
import contextlib
import threading
import queue
import logging
import cv2
import time
from io import BytesIO
import wave
from dashscope.audio.qwen_omni import (
    OmniRealtimeConversation,
    OmniRealtimeCallback,
    MultiModality,
    AudioFormat
)
import dashscope

from dataclasses import dataclass
import yaml
import json

# 配置 logging
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(message)s',
#     handlers=[
#         logging.StreamHandler(sys.stdout)
#     ]
# )

# 加上log输出 便于调试
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('app.log', encoding='utf-8')  # 添加文件处理器
    ]
)
logger = logging.getLogger(__name__) 
# 新加坡和北京地域的API Key不同。获取API Key：c

# 主函数配置的类

@dataclass
class Config:
    config_path: str = './config.yml'
    DASHSCOPE_API_KEY: str = " "
    voice: str = 'Chelsie'  # 默认语音: Chelsie 女声 (支持: Chelsie, Ethan, Aiden)
    # B64PCMPlayer 配置
    sample_rate: int = 24000
    chunk_size_ms: int = 100
    # 音频配置
    audio_sample_rate: int = 16000
    audio_chunk_size: int = 3200
    # 视频配置
    video_fps: float = 1.0  # 帧率配置: >= 1 表示每秒几帧, < 1 表示每 1/fps 秒一帧
    video_max_width: int = 640  # 视频帧最大宽度
    video_start_frame: int = 0  # 从第几帧开始裁剪 (0表示从开头)
    video_end_frame_offset: int = 0  # 从结尾倒数第几帧结束 (0表示到结尾)
    # 模型配置
    model: str = 'qwen3-omni-flash-realtime'
    url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
    transcription_model: str = 'gummy-realtime-v1'
    # 文件配置
    video_path: str = './input.mp4'
    prompt: str = '请描述视频内容'
    supported_video_formats: tuple = ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.m4v')
    evaluator: dict = None
    # 是否保存提取的音频到 wav 文件，便于对比
    save_extracted_audio: bool = False
    extracted_audio_dir: str = './extracted_audio'
    
    def __post_init__(self):
        with open(self.config_path, 'r', encoding='utf-8') as yml_file:
            params = yaml.load(yml_file, Loader=yaml.FullLoader)
            logger.info(f'加载到的配置: {params}   {params['DASHSCOPE_API_KEY']}')
            self.DASHSCOPE_API_KEY = params.get('DASHSCOPE_API_KEY', "")
            self.voice = params.get('voice', self.voice)
            self.sample_rate = params.get('sample_rate', self.sample_rate)
            self.chunk_size_ms = params.get('chunk_size_ms', self.chunk_size_ms)
            self.audio_sample_rate = params.get('audio_sample_rate', self.audio_sample_rate)
            self.audio_chunk_size = params.get('audio_chunk_size', self.audio_chunk_size)
            self.video_fps = params.get('video_fps', self.video_fps)
            self.video_max_width = params.get('video_max_width', self.video_max_width)
            self.video_start_frame = params.get('video_start_frame', self.video_start_frame)
            self.video_end_frame_offset = params.get('video_end_frame_offset', self.video_end_frame_offset)
            self.model = params.get('model', self.model)
            self.url = params.get('url', self.url)
            self.transcription_model = params.get('transcription_model', self.transcription_model)
            self.video_path = params.get('video_path', self.video_path)
            self.prompt = params.get('prompt', self.prompt)
            self.evaluator = params.get('evaluator', {'enabled': False})
            self.save_extracted_audio = params.get('save_extracted_audio', self.save_extracted_audio)
            self.extracted_audio_dir = params.get('extracted_audio_dir', self.extracted_audio_dir)
        
        # 验证视频文件 (仅在非评估模式下)
        if not self.evaluator.get('enabled', False) and not os.path.exists(self.video_path):
            raise FileNotFoundError(f'视频文件不存在: {self.video_path}')
        
        # 检查文件格式 (仅在非评估模式下)
        if not self.evaluator.get('enabled', False):
            file_ext = os.path.splitext(self.video_path)[1].lower()
            if file_ext not in self.supported_video_formats:
                logger.warning(f'警告: 文件格式 {file_ext} 可能不被支持。支持的格式: {", ".join(self.supported_video_formats)}')


# 全局变量
conversation = None
config = None
b64_player = None
video_processor = None

# 这是一个异步音频播放器,专门用于播放 Base64 编码的 PCM 音频数据。它使用了生产者-消费者模式和多线程架构来实现流畅的音频播放。
@dataclass
class B64PCMPlayer:
  pya: pyaudio.PyAudio
  sample_rate: int = 24000
  chunk_size_ms: int = 100
  
  def __post_init__(self):
    self.chunk_size_bytes = self.chunk_size_ms * self.sample_rate * 2 // 1000
    self.player_stream = self.pya.open(format=pyaudio.paInt16,
                                       channels=1,
                                       rate=self.sample_rate,
                                       output=True)
    
    self.raw_audio_buffer: queue.Queue = queue.Queue()
    self.b64_audio_buffer: queue.Queue = queue.Queue()
    self.status_lock = threading.Lock()
    self.status = 'playing'
    self.complete_event: threading.Event = None
    
    self.decoder_thread = threading.Thread(target=self.decoder_loop)
    self.player_thread = threading.Thread(target=self.player_loop)
    self.decoder_thread.start()
    self.player_thread.start()

  def decoder_loop(self):
    while self.status != 'stop':
      recv_audio_b64 = None
      with contextlib.suppress(queue.Empty):
        recv_audio_b64 = self.b64_audio_buffer.get(timeout=0.1)
      if recv_audio_b64 is None:
        continue
      recv_audio_raw = base64.b64decode(recv_audio_b64)
      # 将原始音频数据推入队列，按块处理
      for i in range(0, len(recv_audio_raw), self.chunk_size_bytes):
        chunk = recv_audio_raw[i:i + self.chunk_size_bytes]
        self.raw_audio_buffer.put(chunk)

  def player_loop(self):
    while self.status != 'stop':
      recv_audio_raw = None
      with contextlib.suppress(queue.Empty):
        recv_audio_raw = self.raw_audio_buffer.get(timeout=0.1)
      if recv_audio_raw is None:
        if self.complete_event:
          self.complete_event.set()
        continue
        # 将块写入pyaudio音频播放器，等待播放完这个块
      self.player_stream.write(recv_audio_raw)

  def cancel_playing(self):
    self.b64_audio_buffer.queue.clear()
    self.raw_audio_buffer.queue.clear()

  def add_data(self, data):
    self.b64_audio_buffer.put(data)

  def wait_for_complete(self):
    self.complete_event = threading.Event()
    self.complete_event.wait()
    self.complete_event = None

  def shutdown(self):
    self.status = 'stop'
    self.decoder_thread.join()
    self.player_thread.join()
    self.player_stream.close()


# 视频和音频处理器
@dataclass
class VideoAudioProcessor:
    config: Config
    
    def __post_init__(self):
        self.video_path = self.config.video_path
        self.audio_frames = []
        self.video_frames = []
        self.cap = None
        self.audio_data = None
        
    def extract_audio(self):
        """从视频中提取音频并转换为 16kHz PCM 格式
        
        根据 video_start_frame 和 video_end_frame_offset 裁剪音频
        音频裁剪保持完整采样率，不进行抽帧
        """
        logger.info(f'Extracting audio from {self.video_path}...')
        import subprocess
        try:
            # 首先获取视频信息以计算音频裁剪时间
            cap = cv2.VideoCapture(self.video_path)
            original_fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()
            
            # 计算裁剪时间点
            start_frame = max(0, self.config.video_start_frame)
            end_frame = self.config.video_end_frame_offset
            # end_frame = 1
            
            
            # 验证裁剪参数
            if start_frame >= total_frames:
                start_frame = 0
            if end_frame <= start_frame:
                start_frame = 0
                end_frame = total_frames
            
            # 计算音频裁剪的时间点（秒）
            start_time = start_frame / original_fps if original_fps > 0 else 0
            end_time = end_frame / original_fps if original_fps > 0 else 0
            duration = end_time - start_time
            
            # 构建 ffmpeg 命令，包含音频裁剪参数
            # 优化性能：-ss 在 -i 之前，直接跳转到指定位置，避免解码整个文件
            cmd = [
                'ffmpeg',
                '-loglevel', 'error',  # 减少日志输出
                '-ss', str(start_time),  # 起始时间（放在 -i 之前以提升速度）
                '-t', str(duration),  # 持续时间
                '-i', self.video_path,
                '-vn',  # 不处理视频
                '-acodec', 'pcm_s16le',  # PCM 16-bit
                '-ar', str(self.config.audio_sample_rate),  # 采样率
                '-ac', '1',  # 单声道
                '-f', 'wav',
                '-threads', '0',  # 使用所有可用线程
                '-'  # 输出到 stdout
            ]

            proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            audio_bytes = proc.stdout

            # 通过内存中的字节流读取 wav 数据，避免写入磁盘
            with wave.open(BytesIO(audio_bytes), 'rb') as wf:
                self.audio_data = wf.readframes(wf.getnframes())

            logger.info(f'Audio extracted: {len(self.audio_data)} bytes')
            if start_frame > 0 or self.config.video_end_frame_offset < total_frames:
                logger.info(f'音频已裁剪: {start_time:.2f}s - {end_time:.2f}s (时长 {duration:.2f}s, 完整采样率)')
            else:
                logger.info(f'完整音频 (时长 {duration:.2f}s, 完整采样率)')

            # 如果配置要求，保存 wav 文件以便后续比对
            try:
                if getattr(self.config, 'save_extracted_audio', False):
                    out_dir = getattr(self.config, 'extracted_audio_dir', './extracted_audio') or './extracted_audio'
                    os.makedirs(out_dir, exist_ok=True)
                    base_name = os.path.splitext(os.path.basename(self.video_path))[0]
                    out_path = os.path.join(out_dir, f"{base_name}_extracted.wav")
                    with open(out_path, 'wb') as out_f:
                        out_f.write(audio_bytes)
                    logger.info(f'已保存提取的音频到: {out_path}')
            except Exception as e_save:
                logger.warning(f'保存提取音频失败: {e_save}')

            return self.audio_data

        except Exception as e:
            logger.error(f'✗ 提取音频失败: {e}')
            raise
    
    def extract_video_frames(self):
        """从视频中提取帧
        
        支持的 video_fps 格式：
        - >= 1: 表示每秒提取几帧 (如 1=每秒1帧, 2=每秒2帧, 5=每秒5帧)
        - < 1: 表示每帧的秒数 (如 0.5=2秒1帧, 0.33=3秒1帧, 0.2=5秒1帧)
        
        支持视频裁剪：
        - video_start_frame: 从第几帧开始 (0=从开头)
        - video_end_frame_offset: 从结尾倒数第几帧结束 (0=到结尾)
        """
        logger.info(f'Extracting video frames from {self.video_path}...')
        self.cap = cv2.VideoCapture(self.video_path)
        
        if not self.cap.isOpened():
            raise ValueError(f'Cannot open video file: {self.video_path}')
        
        # 获取视频信息
        original_fps = self.cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / original_fps if original_fps > 0 else 0
        
        # 计算裁剪范围
        start_frame = self.config.video_start_frame
        end_frame = self.config.video_end_frame_offset
        
        # 验证裁剪参数
        if start_frame < 0:
            logger.warning(f'video_start_frame ({start_frame}) < 0, 重置为 0')
            start_frame = 0
        if start_frame >= total_frames:
            logger.warning(f'video_start_frame ({start_frame}) >= 总帧数 ({total_frames}), 重置为 0')
            start_frame = 0
        if end_frame <= start_frame:
            logger.warning(f'裁剪后结束帧 ({end_frame}) <= 起始帧 ({start_frame}), 使用全部视频')
            start_frame = 0
            end_frame = total_frames
        
        # 计算实际处理的帧数和时长
        cropped_frames = end_frame - start_frame
        cropped_duration = cropped_frames / original_fps if original_fps > 0 else 0
        
        # 计算帧间隔 - 支持灵活的 fps 配置
        target_fps = self.config.video_fps
        
        if target_fps >= 1:
            # target_fps >= 1: 表示每秒提取几帧
            if target_fps >= original_fps:
                frame_interval = 1  # 提取所有帧
                logger.info(f'目标帧率 ({target_fps} FPS) >= 原始帧率 ({original_fps:.2f} FPS), 将提取所有帧')
            else:
                frame_interval = int(original_fps / target_fps)
                logger.info(f'配置: 每秒提取 {target_fps} 帧')
        else:
            # target_fps < 1: 表示每 N 秒提取 1 帧 (例如 0.5 = 2秒1帧)
            seconds_per_frame = 1 / target_fps
            frame_interval = int(original_fps * seconds_per_frame)
            logger.info(f'配置: 每 {seconds_per_frame:.2f} 秒提取 1 帧')
        
        # 确保 frame_interval 至少为 1
        frame_interval = max(1, frame_interval)
        
        logger.info(f'视频信息: {original_fps:.2f} FPS, {total_frames} 帧, {duration:.2f} 秒')
        if start_frame > 0 or self.config.video_end_frame_offset > 0:
            logger.info(f'裁剪范围: 第 {start_frame} 帧 到 第 {end_frame} 帧 (共 {cropped_frames} 帧, {cropped_duration:.2f} 秒)')
            logger.info(f'跳过: 开头 {start_frame} 帧 ({start_frame/original_fps:.2f}秒), 结尾 {self.config.video_end_frame_offset} 帧 ({self.config.video_end_frame_offset/original_fps:.2f}秒)')
        logger.info(f'提取设置: 每 {frame_interval} 帧提取 1 帧')
        estimated_frames = int(cropped_frames / frame_interval)
        estimated_fps = estimated_frames / cropped_duration if cropped_duration > 0 else 0
        logger.info(f'预计提取 {estimated_frames} 帧 (平均 {estimated_fps:.3f} FPS)')
        
        frame_count = 0
        extracted_count = 0
        
        # 优化：预计算需要的帧索引，避免重复计算
        target_frames = set()
        for i in range(start_frame, end_frame, frame_interval):
            target_frames.add(i)
        
        # 优化：如果裁剪起始帧大于0，直接跳转到起始位置
        if start_frame > 0:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            frame_count = start_frame
        
        # 预先计算缩放参数（避免每帧都计算）
        ret, first_frame = self.cap.read()
        if not ret:
            logger.error("无法读取视频第一帧")
            return self.video_frames
        
        h, w = first_frame.shape[:2]
        need_resize = w > self.config.video_max_width
        if need_resize:
            ratio = self.config.video_max_width / w
            new_w = self.config.video_max_width
            new_h = int(h * ratio)
        
        # JPEG编码参数（只定义一次）
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 50]
        
        # 处理第一帧（如果需要）
        if frame_count in target_frames:
            if need_resize:
                first_frame = cv2.resize(first_frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
            _, buffer = cv2.imencode('.jpg', first_frame, encode_param)
            frame_b64 = base64.b64encode(buffer).decode('ascii')
            self.video_frames.append(frame_b64)
            extracted_count += 1
        
        frame_count += 1
        
        while frame_count < end_frame:
            ret, frame = self.cap.read()
            if not ret:
                break
            
            # 只处理目标帧
            if frame_count in target_frames:
                # 调整帧大小
                if need_resize:
                    frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
                
                # JPEG编码并转base64
                _, buffer = cv2.imencode('.jpg', frame, encode_param)
                frame_b64 = base64.b64encode(buffer).decode('ascii')
                
                self.video_frames.append(frame_b64)
                extracted_count += 1
            
            frame_count += 1
        
        self.cap.release()
        actual_fps = extracted_count / cropped_duration if cropped_duration > 0 else 0
        logger.info(f'提取完成: 从 {cropped_frames} 帧中提取了 {extracted_count} 帧')
        logger.info(f'实际平均帧率: {actual_fps:.3f} FPS (每 {1/actual_fps:.2f} 秒 1 帧)' if actual_fps > 0 else '提取完成')
        return self.video_frames
    
    def get_audio_chunks(self):
        """将音频数据分块返回"""
        chunk_size = self.config.audio_chunk_size
        for i in range(0, len(self.audio_data), chunk_size):
            yield self.audio_data[i:i + chunk_size]
    
    def cleanup(self):
        """清理资源"""
        if self.cap is not None:
            self.cap.release()


@dataclass
class MyCallback(OmniRealtimeCallback):
    config: Config = None
    
    def __post_init__(self):
        global b64_player
        self.b64_player = b64_player
        self.current_text = ""  # 累积当前响应的文本
        self.response_complete_event = threading.Event() # 用于通知响应完成
        self.last_error = None
    
    def on_open(self) -> None:
        global b64_player
        logger.info('✓ Connection opened (text-only mode, no audio player)\n')
    
    def on_close(self, close_status_code, close_msg) -> None:
        logger.info('\n[Connection Closed] Code: {}, Message: {}'.format(
            close_status_code, close_msg))
        # 在评估模式下不要直接退出进程，记录错误并通知等待的线程
        try:
            if self.config and getattr(self.config, 'evaluator', None) and self.config.evaluator.get('enabled', False):
                self.last_error = f'closed: {close_status_code} {close_msg}'
                if self.response_complete_event:
                    self.response_complete_event.set()
                return
        except Exception:
            pass
        sys.exit(0)

    def on_error(self, error) -> None:
        # websocket 或底层连接出错时的回调
        error_str = str(error)
        try:
            logger.error(f"[WebSocket Error] {error_str}")
            
            # 记录特定错误类型以便调试
            if 'model repeat output' in error_str:
                logger.warning("检测到模型重复输出错误 - 这可能是提示词或输入导致的")
            elif 'timeout' in error_str.lower():
                logger.warning("检测到超时错误 - 网络可能不稳定")
            elif 'Voice' in error_str and 'not supported' in error_str:
                logger.error("语音参数不支持 - 请检查配置文件中的 voice 参数")
        except Exception:
            pass
        self.last_error = error_str
        if self.response_complete_event:
            self.response_complete_event.set()

    def on_event(self, response: str) -> None:
        try:
            global conversation, b64_player
            event_type = response['type']
            
            if event_type == 'session.created':
                logger.info('✓ Session created: {}\n'.format(response['session']['id']))
                
            elif event_type == 'conversation.item.input_audio_transcription.completed':
                logger.info('\n[音频转录] {}\n'.format(response['transcript']))
                
            elif event_type == 'response.created':
                logger.info('\n[AI 响应开始]\n')
                self.current_text = ""  # 重置文本累积
                
            elif event_type == 'response.audio_transcript.delta':
                # 流式输出文本 - 使用 print 保持流式效果
                text = response['delta']
                self.current_text += text
                print(text, end='', flush=True)
                
            elif event_type == 'response.audio_transcript.done':
                # 文本输出完成,换行
                print()  # 换行
                
            elif event_type == 'response.text.delta':
                # 纯文本输出 (如果有) - 使用 print 保持流式效果
                text = response['delta']
                self.current_text += text
                print(text, end='', flush=True)
                
            elif event_type == 'response.text.done':
                print()  # 换行
                
            elif event_type == 'response.audio.delta':
                # 忽略音频数据 (文本模式)
                pass
                    
            elif event_type == 'response.done':
                logger.info('\n' + '=' * 60)
                logger.info('[响应完成]')
                if self.current_text:
                    # 尝试更鲁棒地从文本中提取 JSON（兼容 ```json ... ``` 这种包裹）
                    def try_extract_json(text):
                        import re
                        # 1) 先尝试去掉常见的代码块标记 ```json 或 ```
                        cleaned = re.sub(r'^\s*```[a-zA-Z0-9]*\s*', '', text)
                        cleaned = re.sub(r'\s*```\s*$', '', cleaned)

                        # 2) 找到所有可能的 { 和 } 位置，尝试不同的组合直到 json.loads 成功
                        opens = [m.start() for m in re.finditer(r'\{', cleaned)]
                        closes = [m.start() for m in re.finditer(r'\}', cleaned)]
                        for i in range(len(opens)):
                            for j in range(len(closes)-1, -1, -1):
                                if closes[j] <= opens[i]:
                                    continue
                                candidate = cleaned[opens[i]:closes[j]+1]
                                try:
                                    json.loads(candidate)  # 验证JSON有效性
                                    return candidate
                                except Exception:
                                    continue

                        # 3) 兜底：尝试原始的 first { ... last }
                        if '{' in text and '}' in text:
                            candidate = text[text.find('{'):text.rfind('}')+1]
                            try:
                                json.loads(candidate)
                                return candidate
                            except Exception:
                                return None
                        return None

                    json_part = try_extract_json(self.current_text)
                    if json_part:
                        self.current_text = json_part # 只保留有效的JSON部分
                        logger.info(f'完整JSON: {self.current_text}')
                    else:
                        logger.warning(f'无法解析为JSON, 原始文本: {self.current_text}')

                logger.info('[性能指标]')
                logger.info(f'  - Response ID: {conversation.get_last_response_id()}')
                
                text_delay = conversation.get_last_first_text_delay()
                audio_delay = conversation.get_last_first_audio_delay()
                
                if text_delay is not None:
                    logger.info(f'  - 首字延迟: {text_delay:.0f}ms')
                if audio_delay is not None:
                    logger.info(f'  - 首音延迟: {audio_delay:.0f}ms')
                    
                logger.info('=' * 60)
                self.response_complete_event.set() # 设置事件，通知响应已完成
                
            elif event_type == 'error':
                error_info = response.get('error', {})
                logger.error('\n[错误] {}'.format(error_info))
                
        except Exception as e:
            logger.error('\n[Error in callback] {}'.format(e))
            import traceback
            traceback.print_exc()

def extract_and_process_video(video_path, config):
    """
    第一个函数：特征提取函数。
    负责提取指定视频的音频和视频帧。
    优化：使用并行处理同时提取音频和视频
    """
    logger.info(f"\n[特征提取] 开始处理: {video_path}")
    
    # 覆盖config中的video_path
    temp_config = config
    temp_config.video_path = video_path

    processor = VideoAudioProcessor(config=temp_config)
    timings = {}
    
    try:
        # 使用多线程并行提取音频和视频
        audio_data = None
        video_frames = None
        audio_error = None
        video_error = None
        
        def extract_audio_thread():
            nonlocal audio_data, audio_error
            try:
                audio_data = processor.extract_audio()
            except Exception as e:
                audio_error = e
        
        def extract_video_thread():
            nonlocal video_frames, video_error
            try:
                video_frames = processor.extract_video_frames()
            except Exception as e:
                video_error = e
        
        t0 = time.time()
        
        # 创建并启动两个线程
        audio_thread = threading.Thread(target=extract_audio_thread)
        video_thread = threading.Thread(target=extract_video_thread)
        
        audio_thread.start()
        video_thread.start()
        
        # 等待两个线程完成
        audio_thread.join()
        video_thread.join()
        
        t1 = time.time()
        
        # 检查是否有错误
        if audio_error:
            raise audio_error
        if video_error:
            raise video_error
        
        timings['total_extract_time'] = t1 - t0
        timings['audio_extract_time'] = timings['total_extract_time']  # 并行所以记录总时间
        timings['video_extract_time'] = timings['total_extract_time']

        logger.info(f"✓ [特征提取] 完成: {os.path.basename(video_path)} -> {len(video_frames)} 帧, {len(audio_data)} 字节音频")
        logger.info(f"  - 并行提取总耗时: {timings['total_extract_time']:.3f}s (音频+视频同时进行)")
        return processor, audio_data, video_frames, timings
    except Exception as e:
        logger.error(f"✗ [特征提取] 失败: {video_path}, 原因: {e}")
        return None, None, None, {}
    finally:
        if processor:
            processor.cleanup()


def run_inference(processor, audio_data, video_frames, config):
    """
    第二个函数：检测函数。
    使用提取的视频和音频数据，配合prompt输出回答。
    支持简单重试策略，当发生短暂的 websocket 错误（例如 'model repeat output happened'）时会尝试重连一次。
    返回 (prediction_text, timings_dict)
    """
    global conversation, b64_player
    logger.info("[模型推理] 开始...")

    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            logger.info(f"[模型推理] 第 {attempt} 次尝试...")
        
        callback = MyCallback(config=config)
        conversation = OmniRealtimeConversation(
            model=config.model,
            callback=callback,
            url=config.url
        )

        try:
            conversation.connect()
            conversation.update_session(
                output_modalities=[MultiModality.TEXT], # 评估模式下只输出文本
                voice=config.voice,
                input_audio_format=AudioFormat.PCM_16000HZ_MONO_16BIT,
                output_audio_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
                enable_input_audio_transcription=True,
                input_audio_transcription_model=config.transcription_model,
                enable_turn_detection=False,
                turn_detection_type='server_vad',
            )
            time.sleep(0.5)  # 等待会话建立稳定

            # 发送音频和视频并计时
            t_send_start = time.time()
            
            # ⚠️ 关键：必须先发送音频，再发送视频
            logger.info("[模型推理] 发送音频数据...")
            audio_chunks = list(processor.get_audio_chunks())
            for chunk in audio_chunks:
                audio_b64 = base64.b64encode(chunk).decode('ascii')
                conversation.append_audio(audio_b64)

            logger.info(f"[模型推理] 发送视频帧 ({len(video_frames)} 帧)...")
            for frame_b64 in video_frames:
                conversation.append_video(frame_b64)

            conversation.commit()
            conversation.create_response(
                instructions=config.prompt,
                output_modalities=[MultiModality.TEXT]
            )
            t_send_end = time.time()

            # 等待响应完成并计时
            t_wait_start = time.time()
            callback.response_complete_event.wait(timeout=120) # 等待最多2分钟
            t_wait_end = time.time()

            # 如果 callback 记录了 last_error，视为一次失败并可重试
            if getattr(callback, 'last_error', None):
                logger.warning(f"[模型推理] 检测到回调错误: {callback.last_error}")
                # 清理并在下次尝试前短暂等待
                try:
                    conversation.close()
                except Exception:
                    pass
                try:
                    if b64_player:
                        b64_player.shutdown()
                except Exception:
                    pass
                b64_player = None

                if attempt < max_attempts:
                    logger.info("[模型推理] 将在 1 秒后重试...")
                    time.sleep(1.0)  # 增加等待时间到1秒
                    continue
                else:
                    logger.error("[模型推理] 已达到最大重试次数，放弃")
                    return None, {
                        'send_time': t_send_end - t_send_start,
                        'wait_time': t_wait_end - t_wait_start,
                        'total_inference_time': (t_send_end - t_send_start) + (t_wait_end - t_wait_start)
                    }

            logger.info("✓ [模型推理] 完成.")
            timings = {
                'send_time': t_send_end - t_send_start,
                'wait_time': t_wait_end - t_wait_start,
                'total_inference_time': (t_send_end - t_send_start) + (t_wait_end - t_wait_start)
            }
            return callback.current_text, timings

        except Exception as e:
            logger.error(f"✗ [模型推理] 失败: {e}")
            import traceback
            traceback.print_exc()
            # 清理
            try:
                conversation.close()
            except Exception:
                pass
            try:
                if b64_player:
                    b64_player.shutdown()
            except Exception:
                pass
            b64_player = None

            if attempt < max_attempts:
                logger.info(f"[模型推理] 第 {attempt} 次失败，将在 1 秒后重试...")
                time.sleep(1.0)
                continue
            
            logger.error("[模型推理] 已达到最大重试次数，放弃")
            return None, {}


def evaluate_results(results, config):
    """
    第三个函数：统计函数。
    对比模型输出和真值标签，计算成功率。
    """
    logger.info("\n" + "="*60)
    logger.info("开始评估结果".center(60))
    logger.info("="*60)

    correct_predictions = 0
    total_files = len(results)

    if total_files == 0:
        logger.warning("没有找到评估结果。")
        return

    # per-class 统计
    class_stats = {}

    for result in results:
        video_path = result['video_path']
        prediction_json = result['prediction']

        # 从文件名提取真值标签
        filename = os.path.basename(video_path)
        true_labels=("画画", "做手工", "过家家", "运动")
        true_label=""
        for label in true_labels:
            if label in filename:
                true_label = label
                break
        # # 移除扩展名和可能的数字后缀
        # true_label = ''.join(filter(str.isalpha, os.path.splitext(filename)[0]))

        # 初始化 class_stats
        if true_label not in class_stats:
            class_stats[true_label] = {'total': 0, 'correct': 0}
        class_stats[true_label]['total'] += 1

        try:
            prediction_data = json.loads(prediction_json)
            predicted_label = prediction_data.get('activity_label')

            is_correct = (predicted_label == true_label)
            if is_correct:
                correct_predictions += 1
                class_stats[true_label]['correct'] += 1

            logger.info(f"文件: {filename}")
            logger.info(f"  - 真值: {true_label}")
            logger.info(f"  - 预测: {predicted_label}")
            logger.info(f"  - 结果: {'✓ 正确' if is_correct else '✗ 错误'}")
            logger.info(f"  - 原因: {prediction_data.get('reason', 'N/A')}")
            logger.info("-" * 20)

        except (json.JSONDecodeError, AttributeError) as e:
            logger.error(f"文件: {filename} - 无法解析预测结果或结果格式错误: {prediction_json}, Error: {e}")

    # 计算并输出成功率
    accuracy = (correct_predictions / total_files) * 100 if total_files > 0 else 0
    logger.info("\n" + "="*60)
    logger.info("评估摘要".center(60))
    logger.info(f"总文件数: {total_files}")
    logger.info(f"正确预测数: {correct_predictions}")
    logger.info(f"成功率: {accuracy:.2f}%")

    # 输出每类的正确率
    logger.info('\n每类准确率:'.center(60))
    per_class_results = {}
    for label, stats in class_stats.items():
        total = stats['total']
        correct = stats['correct']
        acc = (correct / total) * 100 if total > 0 else 0
        logger.info(f"  - {label}: {correct}/{total} => {acc:.2f}%")
        per_class_results[label] = {'total': total, 'correct': correct, 'accuracy': round(acc, 2)}

    logger.info("="*60)

    # 保存结果到文件（包含 per-class）
    results_path = config.evaluator.get('results_path', 'eval_results.json')
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump({
            'accuracy': accuracy,
            'total_files': total_files,
            'correct_predictions': correct_predictions,
            'per_class': per_class_results,
            'results': results
        }, f, ensure_ascii=False, indent=4)
    logger.info(f"评估结果已保存到: {results_path}")


def run_evaluator(config):
    """评估器主流程"""
    # 设置 API Key
    dashscope.api_key = config.DASHSCOPE_API_KEY
    
    dataset_path = config.evaluator.get('dataset_path')
    if not dataset_path or not os.path.isdir(dataset_path):
        logger.error(f"数据集路径无效或不是一个文件夹: {dataset_path}")
        return

    all_results = []
    timing_aggregates = {
        'audio_extract_time': 0.0,
        'video_extract_time': 0.0,
        'send_time': 0.0,
        'wait_time': 0.0,
        'total_inference_time': 0.0
    }
    video_files = [f for f in os.listdir(dataset_path) if os.path.splitext(f)[1].lower() in config.supported_video_formats]
    
    logger.info(f"在 {dataset_path} 中找到 {len(video_files)} 个视频文件进行评估。")

    for video_file in video_files:
        video_path = os.path.join(dataset_path, video_file)
        
        # 1. 特征提取
        processor, audio_data, video_frames, timings = extract_and_process_video(video_path, config)
        if not processor:
            continue
            
        # 2. 模型推理
        prediction, inf_timings = run_inference(processor, audio_data, video_frames, config)

        # 如果第一次返回 None，尝试再跑一次（短暂等待后重试一次）
        if prediction is None:
            logger.warning(f"预测为空，尝试对文件重新推理一次: {video_file}")
            try:
                time.sleep(0.3)
                prediction_retry, inf_timings_retry = run_inference(processor, audio_data, video_frames, config)
            except Exception as e:
                logger.error(f"重试时发生异常: {e}")
                prediction_retry, inf_timings_retry = None, {}

            # 如果重试成功，使用重试结果并合并 timings
            if prediction_retry:
                prediction = prediction_retry
                # 合并两个 inf timings（如果存在）
                if inf_timings_retry:
                    # prefer retry timings for send/wait if available
                    inf_timings = {**inf_timings, **inf_timings_retry} if inf_timings else inf_timings_retry
                else:
                    inf_timings = inf_timings or {}
            else:
                logger.warning(f"重试后仍然为空: {video_file}")

        # 合并 timings
        if timings:
            timing_aggregates['audio_extract_time'] += timings.get('audio_extract_time', 0.0)
            timing_aggregates['video_extract_time'] += timings.get('video_extract_time', 0.0)
        if inf_timings:
            timing_aggregates['send_time'] += inf_timings.get('send_time', 0.0)
            timing_aggregates['wait_time'] += inf_timings.get('wait_time', 0.0)
            timing_aggregates['total_inference_time'] += inf_timings.get('total_inference_time', 0.0)

        if prediction:
            all_results.append({
                'video_path': video_path,
                'prediction': prediction,
                'timings': {**timings, **(inf_timings or {})}
            })
        
        # 清理资源
        if processor:
            processor.cleanup()

    # 3. 统计评估
    if all_results:
        evaluate_results(all_results, config)

        # 输出总体耗时统计
        total_videos = len(all_results)
        logger.info('\n' + '='*60)
        logger.info('耗时统计汇总'.center(60))
        logger.info(f"处理视频数量: {total_videos}")
        if total_videos > 0:
            logger.info(f"总音频提取耗时: {timing_aggregates['audio_extract_time']:.3f}s (平均 {timing_aggregates['audio_extract_time']/total_videos:.3f}s/视频)")
            logger.info(f"总视频帧提取耗时: {timing_aggregates['video_extract_time']:.3f}s (平均 {timing_aggregates['video_extract_time']/total_videos:.3f}s/视频)")
            logger.info(f"总发送耗时: {timing_aggregates['send_time']:.3f}s (平均 {timing_aggregates['send_time']/total_videos:.3f}s/视频)")
            logger.info(f"总等待耗时: {timing_aggregates['wait_time']:.3f}s (平均 {timing_aggregates['wait_time']/total_videos:.3f}s/视频)")
            logger.info(f"总推理耗时(发送+等待): {timing_aggregates['total_inference_time']:.3f}s (平均 {timing_aggregates['total_inference_time']/total_videos:.3f}s/视频)")
        logger.info('='*60)

        # 将 timing_aggregates 写入 results 文件中
        results_path = config.evaluator.get('results_path', 'eval_results.json')
        try:
            with open(results_path, 'r', encoding='utf-8') as f:
                prev = json.load(f)
        except Exception:
            prev = {}
        prev['timing_aggregates'] = timing_aggregates
        with open(results_path, 'w', encoding='utf-8') as f:
            json.dump(prev, f, ensure_ascii=False, indent=4)
        logger.info(f"耗时统计已保存到: {results_path} (字段: timing_aggregates)")

def run_single_video(config):
    """单个视频处理主流程"""
    global conversation, b64_player, video_processor
    logger.info('\n[1/6] 初始化配置...')
    dashscope.api_key = config.DASHSCOPE_API_KEY
    
    logger.info(f'  - 视频文件: {config.video_path}')
    logger.info(f'  - 提取帧率: {config.video_fps} FPS')
    logger.info(f'  - 提示词: {config.prompt}')
    
    # 初始化视频音频处理器
    logger.info('\n[2/6] 提取视频和音频...')
    video_processor = VideoAudioProcessor(config=config)
    
    # 提取音频和视频帧 (计时) - 使用并行处理
    try:
        audio_data = None
        video_frames = None
        audio_error = None
        video_error = None
        
        def extract_audio_thread():
            nonlocal audio_data, audio_error
            try:
                audio_data = video_processor.extract_audio()
            except Exception as e:
                audio_error = e
        
        def extract_video_thread():
            nonlocal video_frames, video_error
            try:
                video_frames = video_processor.extract_video_frames()
            except Exception as e:
                video_error = e
        
        t0 = time.time()
        
        # 创建并启动两个线程并行提取
        audio_thread = threading.Thread(target=extract_audio_thread)
        video_thread = threading.Thread(target=extract_video_thread)
        
        audio_thread.start()
        video_thread.start()
        
        # 等待两个线程完成
        audio_thread.join()
        video_thread.join()
        
        t1 = time.time()
        
        # 检查是否有错误
        if audio_error:
            raise audio_error
        if video_error:
            raise video_error
        
        logger.info(f'✓ 提取完成: {len(video_frames)} 帧, {len(audio_data)} 字节音频')
        logger.info(f'  - 并行提取总耗时: {(t1-t0):.3f}s (音频+视频同时进行)')
    except Exception as e:
        logger.error(f'✗ 提取失败: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 初始化回调和会话
    logger.info('\n[3/6] 初始化 AI 会话...')
    callback = MyCallback(config=config)
    conversation = OmniRealtimeConversation(
        model=config.model,
        callback=callback,
        url=config.url
    )
    
    logger.info('[4/6] 连接到服务器...')
    conversation.connect()
    conversation.update_session(
        output_modalities=[MultiModality.TEXT],  # 只输出文本,不输出音频
        voice=config.voice,
        input_audio_format=AudioFormat.PCM_16000HZ_MONO_16BIT,
        output_audio_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
        enable_input_audio_transcription=True,
        input_audio_transcription_model=config.transcription_model,
        enable_turn_detection=False,  # 关闭 VAD,手动控制
        turn_detection_type='server_vad',
    )
    
    def signal_handler(sig, frame):
        logger.info('\n\n[中断] Ctrl+C 按下,正在停止...')
        if conversation:
            conversation.close()
        if b64_player:
            b64_player.shutdown()
        if video_processor:
            video_processor.cleanup()
        logger.info('已停止.')
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        time.sleep(0.5)  # 等待连接稳定 - 增加到0.5秒
        logger.info('\n[5/6] 发送数据到 AI...')
        logger.info('=' * 60)

        # ⚠️ 重要: 必须先发送音频,再发送视频帧 (API要求)
        # 发送音频数据并计时
        logger.info('发送音频数据...')
        t_send_a = time.time()
        audio_chunks = list(video_processor.get_audio_chunks())
        for i, chunk in enumerate(audio_chunks):
            audio_b64 = base64.b64encode(chunk).decode('ascii')
            conversation.append_audio(audio_b64)
            if (i + 1) % 50 == 0 or (i + 1) == len(audio_chunks):
                print(f'  进度: {i+1}/{len(audio_chunks)} 块', end='\r')
        t_send_b = time.time()
        logger.info('\n✓ 所有音频数据已发送')

        # 发送视频帧并计时
        logger.info(f'\n发送视频帧 ({len(video_frames)} 帧)...')
        for i, frame_b64 in enumerate(video_frames):
            conversation.append_video(frame_b64)
            if (i + 1) % 10 == 0 or (i + 1) == len(video_frames):
                print(f'  进度: {i+1}/{len(video_frames)} 帧', end='\r')
        t_send_c = time.time()
        logger.info('\n✓ 所有视频帧已发送')

        # 提交输入并创建响应
        logger.info('\n[6/6] 提交输入并请求响应...')
        logger.info(f'提示词: "{config.prompt}"')
        logger.info('=' * 60)
        conversation.commit()
        conversation.create_response(
            instructions=config.prompt,
            output_modalities=[MultiModality.TEXT]  # 只输出文本
        )

        logger.info('\n等待 AI 响应...\n')
        t_wait_a = time.time()
        callback.response_complete_event.wait(timeout=120)
        t_wait_b = time.time()

        logger.info('\n处理完成!')
        logger.info(f"  - 发送音频耗时: {(t_send_b - t_send_a):.3f}s")
        logger.info(f"  - 发送视频耗时: {(t_send_c - t_send_b):.3f}s")
        logger.info(f"  - 等待响应耗时: {(t_wait_b - t_wait_a):.3f}s")
        
    except Exception as e:
        logger.error(f'\n✗ 处理错误: {e}')
        import traceback
        traceback.print_exc()
    finally:
        if conversation:
            conversation.close()
        if video_processor:
            video_processor.cleanup()
        logger.info('\n程序结束.')


if __name__ == '__main__':
    
    logger.info('=' * 60)
    logger.info('儿童活动情绪检测系统'.center(60))
    logger.info('=' * 60)
    
    config = Config()
    
    if config.evaluator and config.evaluator.get('enabled', False):
        logger.info("评估模式已启用。")
        run_evaluator(config)
    else:
        logger.info("单视频分析模式。")
        run_single_video(config)