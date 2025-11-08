# 儿童语音识别与理解系统
# dashscope SDK 版本需不低于 1.23.9
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
import json

# 配置 logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('asr_app.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 配置类
@dataclass
class Config:
    config_path: str = './config3.yml'
    DASHSCOPE_API_KEY: str = ""
    # 音频配置
    audio_sample_rate: int = 16000
    audio_chunk_size: int = 6400  # 增大chunk提升稳定性
    # 模型配置
    model: str = 'qwen3-omni-flash-realtime'
    url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
    transcription_model: str = 'gummy-realtime-v1'
    # VAD 配置（用于优化语音识别）
    vad_threshold: float = 0.3
    vad_silence_duration_ms: int = 500
    vad_prefix_padding_ms: int = 200
    # 文件配置
    audio_path: str = ''
    prompt: str = '请识别音频内容'
    supported_audio_formats: tuple = ('.mp4', '.m4a', '.wav', '.mp3', '.aac', '.flac')
    evaluator: dict = None
    
    def __post_init__(self):
        with open(self.config_path, 'r', encoding='utf-8') as yml_file:
            params = yaml.load(yml_file, Loader=yaml.FullLoader)
            logger.info(f'加载到的配置: {params["DASHSCOPE_API_KEY"][:10]}...')
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
            self.evaluator = params.get('evaluator', {'enabled': False})
            
            # 如果配置中有 supported_audio_formats，使用配置的
            if 'supported_audio_formats' in params.get('evaluator', {}):
                self.supported_audio_formats = tuple(params['evaluator']['supported_audio_formats'])
        
        # 验证音频文件 (仅在非评估模式下)
        if not self.evaluator.get('enabled', False) and self.audio_path and not os.path.exists(self.audio_path):
            raise FileNotFoundError(f'音频文件不存在: {self.audio_path}')
        
        # 检查文件格式 (仅在非评估模式下)
        if not self.evaluator.get('enabled', False) and self.audio_path:
            file_ext = os.path.splitext(self.audio_path)[1].lower()
            if file_ext not in self.supported_audio_formats:
                logger.warning(f'警告: 文件格式 {file_ext} 可能不被支持。支持的格式: {", ".join(self.supported_audio_formats)}')


# 全局变量
conversation = None
config = None


# 音频处理器
@dataclass
class AudioProcessor:
    config: Config
    
    def __post_init__(self):
        self.audio_path = self.config.audio_path
        self.audio_data = None
        
    def extract_audio(self):
        """从音频/视频文件中提取音频并转换为 16kHz PCM 格式"""
        logger.info(f'正在提取音频: {self.audio_path}...')
        import subprocess
        
        try:
            # 使用 ffmpeg 提取音频并转换为 PCM 格式
            cmd = [
                'ffmpeg',
                '-loglevel', 'error',
                '-i', self.audio_path,
                '-vn',  # 不处理视频
                '-acodec', 'pcm_s16le',  # PCM 16-bit
                '-ar', str(self.config.audio_sample_rate),  # 采样率 16000
                '-ac', '1',  # 单声道
                '-f', 'wav',
                '-'  # 输出到 stdout
            ]
            
            proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            audio_bytes = proc.stdout
            
            # 读取 wav 数据
            with wave.open(BytesIO(audio_bytes), 'rb') as wf:
                self.audio_data = wf.readframes(wf.getnframes())
            
            logger.info(f'✓ 音频提取完成: {len(self.audio_data)} 字节')
            return self.audio_data
            
        except subprocess.CalledProcessError as e:
            logger.error(f'✗ ffmpeg 提取音频失败: {e.stderr.decode()}')
            raise
        except Exception as e:
            logger.error(f'✗ 提取音频失败: {e}')
            raise
    
    def get_audio_chunks(self):
        """将音频数据分块返回，使用配置的chunk_size"""
        if self.audio_data is None:
            raise ValueError("音频数据未提取，请先调用 extract_audio()")
        
        chunk_size = self.config.audio_chunk_size
        for i in range(0, len(self.audio_data), chunk_size):
            yield self.audio_data[i:i + chunk_size]


# 回调处理器
@dataclass
class ASRCallback(OmniRealtimeCallback):
    config: Config = None
    
    def __post_init__(self):
        self.current_text = ""  # 累积当前响应的文本
        self.transcription = ""  # 音频转录文本
        self.response_complete_event = threading.Event()  # 用于通知响应完成
        self.last_error = None
    
    def on_open(self) -> None:
        logger.info('✓ 连接已建立\n')
    
    def on_close(self, close_status_code, close_msg) -> None:
        logger.info(f'\n[连接关闭] Code: {close_status_code}, Message: {close_msg}')
        # 在评估模式下不要直接退出进程
        if self.config and self.config.evaluator.get('enabled', False):
            self.last_error = f'closed: {close_status_code} {close_msg}'
            if self.response_complete_event:
                self.response_complete_event.set()
            return
        sys.exit(0)
    
    def on_error(self, error) -> None:
        error_str = str(error)
        logger.error(f"[错误] {error_str}")
        self.last_error = error_str
        if self.response_complete_event:
            self.response_complete_event.set()
    
    def on_event(self, response: str) -> None:
        try:
            global conversation
            event_type = response['type']
            
            if event_type == 'session.created':
                logger.info('✓ 会话创建成功: {}\n'.format(response['session']['id']))
                
            elif event_type == 'conversation.item.input_audio_transcription.completed':
                # 音频转录完成
                transcription_text = response['transcript']
                self.transcription = transcription_text
                logger.info('\n[音频转录] {}\n'.format(transcription_text))
                
            elif event_type == 'response.created':
                logger.info('\n[AI 分析开始]\n')
                self.current_text = ""
                
            elif event_type == 'response.audio_transcript.delta':
                # 流式文本输出
                text = response['delta']
                self.current_text += text
                print(text, end='', flush=True)
                
            elif event_type == 'response.audio_transcript.done':
                print()  # 换行
                
            elif event_type == 'response.text.delta':
                # 纯文本输出
                text = response['delta']
                self.current_text += text
                print(text, end='', flush=True)
                
            elif event_type == 'response.text.done':
                print()
                
            elif event_type == 'response.done':
                logger.info('\n' + '=' * 60)
                logger.info('[响应完成]')
                
                if self.current_text:
                    # 提取 JSON 内容
                    json_part = self._extract_json(self.current_text)
                    if json_part:
                        self.current_text = json_part
                        logger.info(f'完整JSON: {self.current_text}')
                    else:
                        logger.warning(f'无法解析为JSON, 原始文本: {self.current_text}')
                
                logger.info('[性能指标]')
                logger.info(f'  - Response ID: {conversation.get_last_response_id()}')
                
                text_delay = conversation.get_last_first_text_delay()
                if text_delay is not None:
                    logger.info(f'  - 首字延迟: {text_delay:.0f}ms')
                    
                logger.info('=' * 60)
                self.response_complete_event.set()
                
            elif event_type == 'error':
                error_info = response.get('error', {})
                logger.error('\n[错误] {}'.format(error_info))
                
        except Exception as e:
            logger.error(f'\n[回调错误] {e}')
            import traceback
            traceback.print_exc()
    
    def _extract_json(self, text):
        """从文本中提取 JSON 内容"""
        import re
        
        # 去掉代码块标记
        cleaned = re.sub(r'^\s*```[a-zA-Z0-9]*\s*', '', text)
        cleaned = re.sub(r'\s*```\s*$', '', cleaned)
        
        # 尝试找到 JSON 对象
        opens = [m.start() for m in re.finditer(r'\{', cleaned)]
        closes = [m.start() for m in re.finditer(r'\}', cleaned)]
        
        for i in range(len(opens)):
            for j in range(len(closes) - 1, -1, -1):
                if closes[j] <= opens[i]:
                    continue
                candidate = cleaned[opens[i]:closes[j] + 1]
                try:
                    json.loads(candidate)
                    return candidate
                except Exception:
                    continue
        
        # 兜底
        if '{' in text and '}' in text:
            candidate = text[text.find('{'):text.rfind('}') + 1]
            try:
                json.loads(candidate)
                return candidate
            except Exception:
                return None
        return None


def run_inference(processor, config, max_attempts=2):
    """
    执行语音识别推理
    返回 (transcription, analysis_json, timings_dict)
    """
    global conversation
    logger.info("[语音识别] 开始...")
    
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            logger.info(f"[语音识别] 第 {attempt} 次尝试...")
        
        callback = ASRCallback(config=config)
        conversation = OmniRealtimeConversation(
            model=config.model,
            callback=callback,
            url=config.url
        )
        
        try:
            conversation.connect()
            # 纯语音识别模式：优化VAD参数以提升儿童语音识别准确性
            conversation.update_session(
                output_modalities=[MultiModality.TEXT],  # 只输出文本
                input_audio_format=AudioFormat.PCM_16000HZ_MONO_16BIT,
                output_audio_format=AudioFormat.PCM_16000HZ_MONO_16BIT,  # 必须设置
                enable_input_audio_transcription=True,
                input_audio_transcription_model=config.transcription_model,
                enable_turn_detection=False,  # 启用VAD自动检测
                turn_detection_type='server_vad',
                # turn_detection_threshold=config.vad_threshold,  # VAD阈值（降低可提高灵敏度）
                # turn_detection_silence_duration_ms=config.vad_silence_duration_ms,  # 静音检测时长
                # prefix_padding_ms=config.vad_prefix_padding_ms,  # 前缀填充
                voice='Ethan',  # 必须提供
            )
            time.sleep(0.5)
            
            # 发送音频数据
            t_send_start = time.time()
            logger.info("[语音识别] 发送音频数据...")
            
            audio_chunks = list(processor.get_audio_chunks())
            for i, chunk in enumerate(audio_chunks):
                audio_b64 = base64.b64encode(chunk).decode('ascii')
                conversation.append_audio(audio_b64)
                if (i + 1) % 50 == 0 or (i + 1) == len(audio_chunks):
                    print(f'  进度: {i + 1}/{len(audio_chunks)} 块', end='\r')
            
            print()  # 换行
            t_send_end = time.time()
            
            # 提交并请求分析
            logger.info("[语音识别] 请求 AI 分析...")
            conversation.commit()
            conversation.create_response(
                instructions=config.prompt,
                output_modalities=[MultiModality.TEXT]
            )
            
            # 等待响应
            t_wait_start = time.time()
            callback.response_complete_event.wait(timeout=120)
            t_wait_end = time.time()
            
            # 检查错误
            if callback.last_error:
                logger.warning(f"[语音识别] 检测到错误: {callback.last_error}")
                conversation.close()
                
                if attempt < max_attempts:
                    logger.info("[语音识别] 将在 1 秒后重试...")
                    time.sleep(1.0)
                    continue
                else:
                    logger.error("[语音识别] 已达到最大重试次数")
                    return None, None, {}
            
            logger.info("✓ [语音识别] 完成")
            
            timings = {
                'send_time': t_send_end - t_send_start,
                'wait_time': t_wait_end - t_wait_start,
                'total_time': (t_send_end - t_send_start) + (t_wait_end - t_wait_start)
            }
            
            return callback.transcription, callback.current_text, timings
            
        except Exception as e:
            logger.error(f"✗ [语音识别] 失败: {e}")
            import traceback
            traceback.print_exc()
            
            try:
                conversation.close()
            except Exception:
                pass
            
            if attempt < max_attempts:
                logger.info(f"[语音识别] 第 {attempt} 次失败，将在 1 秒后重试...")
                time.sleep(1.0)
                continue
            
            logger.error("[语音识别] 已达到最大重试次数")
            return None, None, {}


def evaluate_results(results, config):
    """评估结果统计 - 针对ASR任务优化"""
    logger.info("\n" + "=" * 60)
    logger.info("儿童语音识别评估结果".center(60))
    logger.info("=" * 60)
    
    total_files = len(results)
    if total_files == 0:
        logger.warning("没有找到评估结果。")
        return
    
    # 统计各项指标
    stats = {
        'total': total_files,
        'success': 0,
        'challenges': {},
        'emotions': {},
        'intents': {},
        'avg_confidence': 0.0,
        'avg_keywords': 0.0
    }
    
    logger.info(f"\n处理文件总数: {total_files}")
    logger.info("\n" + "-" * 60)
    logger.info("详细结果:")
    logger.info("-" * 60)
    
    for i, result in enumerate(results, 1):
        audio_path = result['audio_path']
        filename = os.path.basename(audio_path)
        transcription = result.get('transcription', 'N/A')
        analysis = result.get('analysis', 'N/A')
        
        logger.info(f"\n[{i}/{total_files}] 📁 {filename}")
        logger.info(f"  🎤 原始转录: {transcription}")
        
        try:
            analysis_data = json.loads(analysis) if isinstance(analysis, str) else analysis
            stats['success'] += 1
            
            # 核心信息
            logger.info(f"  ✅ 修正文本: {analysis_data.get('transcription', 'N/A')}")
            logger.info(f"  📝 原始文本: {analysis_data.get('raw_transcription', 'N/A')}")
            
            # 关键词
            keywords = analysis_data.get('key_words', [])
            stats['avg_keywords'] += len(keywords)
            logger.info(f"  🔑 关键词({len(keywords)}个): {', '.join(keywords)}")
            
            # 意图和情绪
            intent = analysis_data.get('intent', 'N/A')
            emotion = analysis_data.get('emotion', 'N/A')
            stats['intents'][intent] = stats['intents'].get(intent, 0) + 1
            stats['emotions'][emotion] = stats['emotions'].get(emotion, 0) + 1
            logger.info(f"  💡 意图: {intent}")
            logger.info(f"  😊 情绪: {emotion}")
            
            # 识别挑战
            challenges = analysis_data.get('challenges', [])
            for challenge in challenges:
                stats['challenges'][challenge] = stats['challenges'].get(challenge, 0) + 1
            logger.info(f"  ⚠️  识别挑战({len(challenges)}个): {', '.join(challenges) if challenges else '无'}")
            
            # 语义补全
            context = analysis_data.get('context_completion', '')
            if context:
                logger.info(f"  🧩 语义补全: {context}")
            
            # 置信度
            confidence = analysis_data.get('confidence_score', 0.0)
            stats['avg_confidence'] += confidence
            logger.info(f"  📊 置信度: {confidence:.2%}")
            
            # 反馈
            feedback = analysis_data.get('feedback', 'N/A')
            logger.info(f"  💬 反馈: {feedback}")
            
        except Exception as e:
            logger.error(f"  ✗ 无法解析分析结果: {e}")
        
        logger.info("-" * 60)
    
    # 统计摘要
    if stats['success'] > 0:
        stats['avg_confidence'] /= stats['success']
        stats['avg_keywords'] /= stats['success']
    
    logger.info("\n" + "=" * 60)
    logger.info("统计摘要".center(60))
    logger.info("=" * 60)
    logger.info(f"✅ 成功解析: {stats['success']}/{total_files} ({stats['success']/total_files*100:.1f}%)")
    logger.info(f"📊 平均置信度: {stats['avg_confidence']:.2%}")
    logger.info(f"🔑 平均关键词数: {stats['avg_keywords']:.1f}个")
    
    # 识别挑战统计
    if stats['challenges']:
        logger.info("\n⚠️  识别挑战分布:")
        for challenge, count in sorted(stats['challenges'].items(), key=lambda x: x[1], reverse=True):
            logger.info(f"  - {challenge}: {count}次 ({count/total_files*100:.1f}%)")
    
    # 情绪分布
    if stats['emotions']:
        logger.info("\n😊 情绪分布:")
        for emotion, count in sorted(stats['emotions'].items(), key=lambda x: x[1], reverse=True):
            logger.info(f"  - {emotion}: {count}次 ({count/total_files*100:.1f}%)")
    
    # 意图分布
    if stats['intents']:
        logger.info("\n💡 意图分布:")
        for intent, count in sorted(stats['intents'].items(), key=lambda x: x[1], reverse=True):
            logger.info(f"  - {intent}: {count}次 ({count/total_files*100:.1f}%)")
    
    logger.info("=" * 60)
    
    # 保存结果
    results_path = config.evaluator.get('results_path', 'eval_results_asr.json')
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump({
            'total_files': total_files,
            'statistics': stats,
            'results': results
        }, f, ensure_ascii=False, indent=4)
    
    logger.info(f"\n💾 评估结果已保存到: {results_path}")
    logger.info("=" * 60)


def run_evaluator(config):
    """评估器主流程"""
    dashscope.api_key = config.DASHSCOPE_API_KEY
    
    dataset_path = config.evaluator.get('dataset_path')
    if not dataset_path or not os.path.isdir(dataset_path):
        logger.error(f"数据集路径无效: {dataset_path}")
        return
    
    # 查找所有音频文件
    audio_files = [
        f for f in os.listdir(dataset_path)
        if os.path.splitext(f)[1].lower() in config.supported_audio_formats
    ]
    
    logger.info(f"在 {dataset_path} 中找到 {len(audio_files)} 个音频文件")
    
    all_results = []
    timing_aggregates = {'send_time': 0.0, 'wait_time': 0.0, 'total_time': 0.0}
    
    for audio_file in audio_files:
        audio_path = os.path.join(dataset_path, audio_file)
        logger.info(f"\n{'=' * 60}")
        logger.info(f"处理文件: {audio_file}")
        logger.info('=' * 60)
        
        # 更新配置中的音频路径
        temp_config = config
        temp_config.audio_path = audio_path
        
        # 提取音频
        processor = AudioProcessor(config=temp_config)
        try:
            t0 = time.time()
            processor.extract_audio()
            t1 = time.time()
            extract_time = t1 - t0
            logger.info(f"音频提取耗时: {extract_time:.3f}s")
        except Exception as e:
            logger.error(f"✗ 音频提取失败: {e}")
            continue
        
        # 执行推理
        transcription, analysis, timings = run_inference(processor, temp_config)
        
        # 如果失败，重试一次
        if transcription is None:
            logger.warning("首次推理失败，重试中...")
            time.sleep(0.5)
            transcription, analysis, timings = run_inference(processor, temp_config)
        
        if transcription:
            all_results.append({
                'audio_path': audio_path,
                'transcription': transcription,
                'analysis': analysis,
                'timings': timings
            })
            
            # 累计时间统计
            for key in timing_aggregates:
                timing_aggregates[key] += timings.get(key, 0.0)
    
    # 评估结果
    if all_results:
        evaluate_results(all_results, config)
        
        # 输出时间统计
        logger.info("\n" + "=" * 60)
        logger.info("耗时统计汇总".center(60))
        logger.info(f"处理文件数: {len(all_results)}")
        if len(all_results) > 0:
            logger.info(f"总发送耗时: {timing_aggregates['send_time']:.3f}s (平均 {timing_aggregates['send_time'] / len(all_results):.3f}s/文件)")
            logger.info(f"总等待耗时: {timing_aggregates['wait_time']:.3f}s (平均 {timing_aggregates['wait_time'] / len(all_results):.3f}s/文件)")
            logger.info(f"总推理耗时: {timing_aggregates['total_time']:.3f}s (平均 {timing_aggregates['total_time'] / len(all_results):.3f}s/文件)")
        logger.info("=" * 60)


def run_single_audio(config):
    """单个音频文件处理"""
    global conversation
    
    logger.info('\n[1/4] 初始化配置...')
    dashscope.api_key = config.DASHSCOPE_API_KEY
    logger.info(f'  - 音频文件: {config.audio_path}')
    
    logger.info('\n[2/4] 提取音频...')
    processor = AudioProcessor(config=config)
    
    try:
        processor.extract_audio()
    except Exception as e:
        logger.error(f'✗ 音频提取失败: {e}')
        sys.exit(1)
    
    logger.info('\n[3/4] 初始化 AI 会话...')
    callback = ASRCallback(config=config)
    conversation = OmniRealtimeConversation(
        model=config.model,
        callback=callback,
        url=config.url
    )
    
    logger.info('[4/4] 连接并发送数据...')
    
    def signal_handler(sig, frame):
        logger.info('\n\n[中断] Ctrl+C 按下，正在停止...')
        if conversation:
            conversation.close()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        conversation.connect()
        # 纯语音识别模式：优化VAD参数
        conversation.update_session(
            output_modalities=[MultiModality.TEXT],
            input_audio_format=AudioFormat.PCM_16000HZ_MONO_16BIT,
            output_audio_format=AudioFormat.PCM_16000HZ_MONO_16BIT,  # 必须设置
            enable_input_audio_transcription=True,
            input_audio_transcription_model=config.transcription_model,
            enable_turn_detection=True,  # 启用VAD
            turn_detection_type='server_vad',
            turn_detection_threshold=config.vad_threshold,
            turn_detection_silence_duration_ms=config.vad_silence_duration_ms,
            prefix_padding_ms=config.vad_prefix_padding_ms,
            voice='Ethan',  # 必须提供
        )
        
        time.sleep(0.5)
        
        logger.info('\n发送音频数据...')
        logger.info('=' * 60)
        
        audio_chunks = list(processor.get_audio_chunks())
        for i, chunk in enumerate(audio_chunks):
            audio_b64 = base64.b64encode(chunk).decode('ascii')
            conversation.append_audio(audio_b64)
            if (i + 1) % 50 == 0 or (i + 1) == len(audio_chunks):
                print(f'  进度: {i + 1}/{len(audio_chunks)} 块', end='\r')
        
        print()
        logger.info('✓ 音频数据已发送')
        
        logger.info('\n提交输入并请求分析...')
        logger.info(f'提示词: "{config.prompt[:100]}..."')
        logger.info('=' * 60)
        
        conversation.commit()
        conversation.create_response(
            instructions=config.prompt,
            output_modalities=[MultiModality.TEXT]
        )
        
        logger.info('\n等待 AI 响应...\n')
        callback.response_complete_event.wait(timeout=120)
        
        logger.info('\n处理完成!')
        
    except Exception as e:
        logger.error(f'\n✗ 处理错误: {e}')
        import traceback
        traceback.print_exc()
    finally:
        if conversation:
            conversation.close()
        logger.info('\n程序结束.')


if __name__ == '__main__':
    logger.info('=' * 60)
    logger.info('儿童语音识别与理解系统'.center(60))
    logger.info('=' * 60)
    
    config = Config()
    
    if config.evaluator and config.evaluator.get('enabled', False):
        logger.info("评估模式已启用。")
        run_evaluator(config)
    else:
        logger.info("单音频分析模式。")
        run_single_audio(config)
