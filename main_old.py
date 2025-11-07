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
from io import BytesIO
from PIL import Image
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
# 新加坡和北京地域的API Key不同。获取API Key：https://www.alibabacloud.com/help/zh/model-studio/get-api-key

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
        
        # 验证视频文件
        if not os.path.exists(self.video_path):
            raise FileNotFoundError(f'视频文件不存在: {self.video_path}')
        
        # 检查文件格式
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
        
        注意：音频不进行裁剪，保持完整性
        """
        logger.info(f'Extracting audio from {self.video_path}...')
        import subprocess
        import tempfile
        
        # 创建临时文件保存提取的音频
        temp_audio = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        temp_audio_path = temp_audio.name
        temp_audio.close()
        
        try:
            # 使用 ffmpeg 提取音频并转换为 16kHz 单声道 PCM
            # 不添加裁剪参数，保持音频完整
            cmd = [
                'ffmpeg', '-i', self.video_path,
                '-vn',  # 不处理视频
                '-acodec', 'pcm_s16le',  # PCM 16-bit
                '-ar', str(self.config.audio_sample_rate),  # 采样率
                '-ac', '1',  # 单声道
                '-y', temp_audio_path  # 覆盖输出文件
            ]
            
            subprocess.run(cmd, check=True, capture_output=True)
            
            # 读取音频数据
            with wave.open(temp_audio_path, 'rb') as wf:
                self.audio_data = wf.readframes(wf.getnframes())
            
            logger.info(f'Audio extracted: {len(self.audio_data)} bytes (完整音频，未裁剪)')
            return self.audio_data
            
        finally:
            # 清理临时文件
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
    
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
        
        while True:
            ret, frame = self.cap.read()
            if not ret:
                break
            
            # 检查是否在裁剪范围内
            if frame_count < start_frame:
                frame_count += 1
                continue
            if frame_count >= end_frame:
                break
            
            # 计算相对于裁剪起始位置的帧索引
            relative_frame = frame_count - start_frame
            
            if relative_frame % frame_interval == 0:
                # 调整帧大小
                h, w = frame.shape[:2]
                if w > self.config.video_max_width:
                    ratio = self.config.video_max_width / w
                    new_w = self.config.video_max_width
                    new_h = int(h * ratio)
                    frame = cv2.resize(frame, (new_w, new_h))
                
                # 转换为 JPEG 格式
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame_rgb)
                buffer = BytesIO()
                img.save(buffer, format='JPEG', quality=85)
                frame_b64 = base64.b64encode(buffer.getvalue()).decode('ascii')
                
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
    
    def on_open(self) -> None:
        global b64_player
        logger.info('✓ Connection opened, initializing audio player...')
        pya = pyaudio.PyAudio()
        b64_player = B64PCMPlayer(
            pya=pya,
            sample_rate=self.config.sample_rate,
            chunk_size_ms=self.config.chunk_size_ms
        )
        self.b64_player = b64_player
        logger.info('✓ Audio player initialized\n')
    
    def on_close(self, close_status_code, close_msg) -> None:
        logger.info('\n[Connection Closed] Code: {}, Message: {}'.format(
            close_status_code, close_msg))
        sys.exit(0)

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
                # 接收音频数据
                recv_audio_b64 = response['delta']
                if b64_player:
                    b64_player.add_data(recv_audio_b64)
                    
            elif event_type == 'response.done':
                logger.info('\n' + '=' * 60)
                logger.info('[响应完成]')
                if self.current_text:
                    logger.info(f'完整文本: {self.current_text}')
                logger.info('[性能指标]')
                logger.info(f'  - Response ID: {conversation.get_last_response_id()}')
                logger.info(f'  - 首字延迟: {conversation.get_last_first_text_delay():.0f}ms')
                logger.info(f'  - 首音延迟: {conversation.get_last_first_audio_delay():.0f}ms')
                logger.info('=' * 60)
                
            elif event_type == 'error':
                error_info = response.get('error', {})
                logger.error('\n[错误] {}'.format(error_info))
                
        except Exception as e:
            logger.error('\n[Error in callback] {}'.format(e))
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    
    logger.info('=' * 60)
    logger.info('儿童活动情绪检测系统'.center(60))
    logger.info('=' * 60)
    
    logger.info('\n[1/6] 初始化配置...')
    config = Config()
    dashscope.api_key = config.DASHSCOPE_API_KEY
    
    logger.info(f'  - 视频文件: {config.video_path}')
    logger.info(f'  - 提取帧率: {config.video_fps} FPS')
    logger.info(f'  - 提示词: {config.prompt}')
    
    # 初始化视频音频处理器
    logger.info('\n[2/6] 提取视频和音频...')
    video_processor = VideoAudioProcessor(config=config)
    
    # 提取音频和视频帧
    try:
        audio_data = video_processor.extract_audio()
        video_frames = video_processor.extract_video_frames()
        logger.info(f'✓ 提取完成: {len(video_frames)} 帧, {len(audio_data)} 字节音频')
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
        output_modalities=[MultiModality.AUDIO, MultiModality.TEXT],  # 输出音频和文本
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
        conversation.close()
        if b64_player:
            b64_player.shutdown()
        if video_processor:
            video_processor.cleanup()
        logger.info('已停止.')
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        import time
        time.sleep(1)  # 等待连接稳定
        
        logger.info('\n[5/6] 发送数据到 AI...')
        logger.info('=' * 60)
        
        # ⚠️ 重要: 必须先发送音频,再发送视频帧
        # 发送音频数据
        logger.info('发送音频数据...')
        audio_chunks = list(video_processor.get_audio_chunks())
        for i, chunk in enumerate(audio_chunks):
            audio_b64 = base64.b64encode(chunk).decode('ascii')
            conversation.append_audio(audio_b64)
            if (i + 1) % 50 == 0 or (i + 1) == len(audio_chunks):
                print(f'  进度: {i+1}/{len(audio_chunks)} 块', end='\r')
        logger.info('\n✓ 所有音频数据已发送')
        
        # 发送视频帧
        logger.info(f'\n发送视频帧 ({len(video_frames)} 帧)...')
        for i, frame_b64 in enumerate(video_frames):
            conversation.append_video(frame_b64)
            if (i + 1) % 10 == 0 or (i + 1) == len(video_frames):
                print(f'  进度: {i+1}/{len(video_frames)} 帧', end='\r')
        logger.info('\n✓ 所有视频帧已发送')
        
        # 提交输入并创建响应
        logger.info('\n[6/6] 提交输入并请求响应...')
        logger.info(f'提示词: "{config.prompt}"')
        logger.info('=' * 60)
        conversation.commit()
        conversation.create_response(
            instructions=config.prompt,
            output_modalities=[MultiModality.AUDIO, MultiModality.TEXT]
        )
        
        logger.info('\n等待 AI 响应...\n')
        
        # 等待响应完成
        while True:
            if conversation.last_message and conversation.last_message.get('type') == 'response.done':
                break
            time.sleep(0.1)
        
        logger.info('\n处理完成! 按 Ctrl+C 退出或等待音频播放完成...')
        
        # 等待音频播放完成
        if b64_player:
            time.sleep(3)  # 给音频播放留一些时间
        
    except Exception as e:
        logger.error(f'\n✗ 处理错误: {e}')
        import traceback
        traceback.print_exc()
    finally:
        conversation.close()
        if b64_player:
            b64_player.shutdown()
        if video_processor:
            video_processor.cleanup()
        logger.info('\n程序结束.')