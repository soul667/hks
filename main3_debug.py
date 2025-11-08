# 调试版本 - 纯 logging 输出,不做解析
import os
import base64
import signal
import sys
import threading
import logging
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

# 配置 logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('debug_output.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 配置类
@dataclass
class Config:
    config_path: str = './config3.yml'
    DASHSCOPE_API_KEY: str = ""
    audio_sample_rate: int = 16000
    audio_chunk_size: int = 6400
    model: str = 'qwen3-omni-flash-realtime'
    url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
    transcription_model: str = 'gummy-realtime-v1'
    vad_threshold: float = 0.3
    vad_silence_duration_ms: int = 500
    vad_prefix_padding_ms: int = 200
    audio_path: str = ''
    prompt: str = '请识别音频内容'
    
    def __post_init__(self):
        with open(self.config_path, 'r', encoding='utf-8') as yml_file:
            params = yaml.load(yml_file, Loader=yaml.FullLoader)
            logger.info(f'加载配置文件: {self.config_path}')
            self.DASHSCOPE_API_KEY = params.get('DASHSCOPE_API_KEY', "")
            self.audio_sample_rate = params.get('audio_sample_rate', self.audio_sample_rate)
            self.audio_chunk_size = params.get('audio_chunk_size', self.audio_chunk_size)
            self.model = params.get('model', self.model)
            self.url = params.get('url', self.url)
            self.transcription_model = params.get('transcription_model', self.transcription_model)
            self.vad_threshold = params.get('vad_threshold', self.vad_threshold)
            self.vad_silence_duration_ms = params.get('vad_silence_duration_ms', self.vad_silence_duration_ms)
            self.vad_prefix_padding_ms = params.get('vad_prefix_padding_ms', self.vad_prefix_padding_ms)
            self.audio_path = params.get('audio_path', self.audio_path)
            self.prompt = params.get('prompt', self.prompt)
            
            logger.info(f'API Key: {self.DASHSCOPE_API_KEY[:10]}...')
            logger.info(f'Model: {self.model}')
            logger.info(f'Audio Path: {self.audio_path}')
        
        if self.audio_path and not os.path.exists(self.audio_path):
            raise FileNotFoundError(f'音频文件不存在: {self.audio_path}')


# 音频处理器
@dataclass
class AudioProcessor:
    config: Config
    
    def __post_init__(self):
        self.audio_path = self.config.audio_path
        self.audio_data = None
        
    def extract_audio(self):
        """从音频/视频文件中提取音频并转换为 16kHz PCM 格式"""
        logger.info(f'开始提取音频: {self.audio_path}')
        import subprocess
        
        try:
            cmd = [
                'ffmpeg',
                '-loglevel', 'error',
                '-i', self.audio_path,
                '-vn',
                '-acodec', 'pcm_s16le',
                '-ar', str(self.config.audio_sample_rate),
                '-ac', '1',
                '-f', 'wav',
                '-'
            ]
            
            logger.debug(f'FFmpeg命令: {" ".join(cmd)}')
            proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            audio_bytes = proc.stdout
            
            with wave.open(BytesIO(audio_bytes), 'rb') as wf:
                self.audio_data = wf.readframes(wf.getnframes())
            
            logger.info(f'音频提取完成: {len(self.audio_data)} 字节')
            return self.audio_data
            
        except subprocess.CalledProcessError as e:
            logger.error(f'FFmpeg提取失败: {e.stderr.decode()}')
            raise
        except Exception as e:
            logger.error(f'音频提取异常: {e}')
            raise
    
    def get_audio_chunks(self):
        """将音频数据分块"""
        if self.audio_data is None:
            raise ValueError("音频数据未提取")
        
        chunk_size = self.config.audio_chunk_size
        logger.info(f'音频分块大小: {chunk_size} 字节')
        total_chunks = (len(self.audio_data) + chunk_size - 1) // chunk_size
        logger.info(f'总块数: {total_chunks}')
        
        for i in range(0, len(self.audio_data), chunk_size):
            yield self.audio_data[i:i + chunk_size]


# 回调处理器 - 纯 logging,不做解析
@dataclass
class DebugCallback(OmniRealtimeCallback):
    config: Config = None
    
    def __post_init__(self):
        self.response_complete_event = threading.Event()
        self.last_error = None
    
    def on_open(self) -> None:
        logger.info('='*80)
        logger.info('WebSocket 连接已建立')
        logger.info('='*80)
    
    def on_close(self, close_status_code, close_msg) -> None:
        logger.info('='*80)
        logger.info(f'WebSocket 连接关闭')
        logger.info(f'  关闭状态码: {close_status_code}')
        logger.info(f'  关闭消息: {close_msg}')
        logger.info('='*80)
        sys.exit(0)
    
    def on_error(self, error) -> None:
        logger.error('='*80)
        logger.error(f'发生错误: {error}')
        logger.error('='*80)
        self.last_error = str(error)
        self.response_complete_event.set()
    
    def on_event(self, response: str) -> None:
        """纯 logging 输出所有事件"""
        try:
            event_type = response.get('type', 'UNKNOWN')
            
            logger.info('-'*80)
            logger.info(f'事件类型: {event_type}')
            logger.info(f'完整事件数据:')
            
            # 递归打印所有字段
            self._log_dict(response, indent=2)
            logger.info('-'*80)
            
            # 特殊标记响应完成
            if event_type == 'response.done':
                logger.info('*'*80)
                logger.info('响应完成事件触发')
                logger.info('*'*80)
                self.response_complete_event.set()
                
        except Exception as e:
            logger.error(f'回调处理异常: {e}')
            import traceback
            logger.error(traceback.format_exc())
    
    def _log_dict(self, d, indent=0):
        """递归打印字典内容"""
        prefix = '  ' * indent
        if isinstance(d, dict):
            for key, value in d.items():
                if isinstance(value, (dict, list)):
                    logger.info(f'{prefix}{key}:')
                    self._log_dict(value, indent + 1)
                else:
                    logger.info(f'{prefix}{key}: {value}')
        elif isinstance(d, list):
            for i, item in enumerate(d):
                logger.info(f'{prefix}[{i}]:')
                self._log_dict(item, indent + 1)
        else:
            logger.info(f'{prefix}{d}')


def main():
    logger.info('='*80)
    logger.info('调试模式 - 纯 logging 输出')
    logger.info('='*80)
    
    # 加载配置
    config = Config()
    dashscope.api_key = config.DASHSCOPE_API_KEY
    
    # 提取音频
    logger.info('\n步骤 1: 提取音频')
    logger.info('='*80)
    processor = AudioProcessor(config=config)
    
    try:
        processor.extract_audio()
    except Exception as e:
        logger.error(f'音频提取失败: {e}')
        sys.exit(1)
    
    # 初始化会话
    logger.info('\n步骤 2: 初始化 WebSocket 会话')
    logger.info('='*80)
    callback = DebugCallback(config=config)
    conversation = OmniRealtimeConversation(
        model=config.model,
        callback=callback,
        url=config.url
    )
    
    def signal_handler(sig, frame):
        logger.info('\n收到中断信号,正在关闭...')
        if conversation:
            conversation.close()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # 连接
        logger.info('正在连接...')
        conversation.connect()
        
        # 配置会话
        logger.info('\n步骤 3: 配置会话参数')
        logger.info('='*80)
        logger.info(f'  output_modalities: TEXT')
        logger.info(f'  input_audio_format: PCM_16000HZ_MONO_16BIT')
        logger.info(f'  enable_input_audio_transcription: True')
        logger.info(f'  transcription_model: {config.transcription_model}')
        logger.info(f'  enable_turn_detection: True')
        logger.info(f'  vad_threshold: {config.vad_threshold}')
        logger.info(f'  vad_silence_duration_ms: {config.vad_silence_duration_ms}')
        logger.info(f'  prefix_padding_ms: {config.vad_prefix_padding_ms}')
        
        conversation.update_session(
            output_modalities=[MultiModality.TEXT],
            input_audio_format=AudioFormat.PCM_16000HZ_MONO_16BIT,
            output_audio_format=AudioFormat.PCM_16000HZ_MONO_16BIT,
            enable_input_audio_transcription=True,
            input_audio_transcription_model=config.transcription_model,
            enable_turn_detection=False,
            turn_detection_type='server_vad',
            turn_detection_threshold=config.vad_threshold,
            turn_detection_silence_duration_ms=config.vad_silence_duration_ms,
            prefix_padding_ms=config.vad_prefix_padding_ms,
            voice='Ethan',
        )
        
        time.sleep(0.5)
        
        # 发送音频
        logger.info('\n步骤 4: 发送音频数据')
        logger.info('='*80)
        
        audio_chunks = list(processor.get_audio_chunks())
        logger.info(f'开始发送 {len(audio_chunks)} 块音频数据')
        
        for i, chunk in enumerate(audio_chunks):
            audio_b64 = base64.b64encode(chunk).decode('ascii')
            conversation.append_audio(audio_b64)
            
            if (i + 1) % 10 == 0:
                logger.debug(f'已发送 {i + 1}/{len(audio_chunks)} 块')
        
        logger.info(f'所有音频数据已发送 ({len(audio_chunks)} 块)')
        
        # 关闭 VAD,防止检测到后续语音时取消响应
        logger.info('\n关闭 VAD (防止多段语音干扰)')
        # 提交并请求响应
        logger.info('\n步骤 5: 提交音频并请求分析')
        logger.info('='*80)
        logger.info(f'提示词: {config.prompt}')
        
        conversation.commit()
        conversation.create_response(
            instructions=config.prompt,
            output_modalities=[MultiModality.TEXT]
        )
        
        # 等待响应
        logger.info('\n步骤 6: 等待 AI 响应')
        logger.info('='*80)
        logger.info('开始等待响应事件...\n')
        
        callback.response_complete_event.wait(timeout=120)
        
        logger.info('\n'+'='*80)
        logger.info('处理完成')
        logger.info('='*80)
        
    except Exception as e:
        logger.error(f'处理异常: {e}')
        import traceback
        logger.error(traceback.format_exc())
    finally:
        if conversation:
            conversation.close()
        logger.info('\n程序结束')


if __name__ == '__main__':
    main()
