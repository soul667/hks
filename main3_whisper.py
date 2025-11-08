# Whisper 语音识别测试
import os
import logging
import sys
import time
from dataclasses import dataclass
import yaml
import json
import whisper

# 配置 logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('whisper_output.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 配置类
@dataclass
class Config:
    config_path: str = './config3.yml'
    audio_path: str = ''
    model_name: str = 'base'  # tiny, base, small, medium, large
    language: str = 'zh'  # 中文
    task: str = 'transcribe'  # transcribe 或 translate
    supported_audio_formats: tuple = ('.mp4', '.m4a', '.wav', '.mp3', '.aac', '.flac')
    evaluator: dict = None
    
    def __post_init__(self):
        with open(self.config_path, 'r', encoding='utf-8') as yml_file:
            params = yaml.load(yml_file, Loader=yaml.FullLoader)
            logger.info(f'加载配置文件: {self.config_path}')
            
            self.audio_path = params.get('audio_path', self.audio_path)
            self.evaluator = params.get('evaluator', {'enabled': False})
            
            # Whisper 特定配置
            whisper_config = params.get('whisper', {})
            self.model_name = whisper_config.get('model_name', self.model_name)
            self.language = whisper_config.get('language', self.language)
            self.task = whisper_config.get('task', self.task)
            
            logger.info(f'Whisper 模型: {self.model_name}')
            logger.info(f'语言: {self.language}')
            logger.info(f'任务: {self.task}')
            logger.info(f'音频文件: {self.audio_path}')
            
            # 如果配置中有 supported_audio_formats，使用配置的
            if 'supported_audio_formats' in self.evaluator:
                self.supported_audio_formats = tuple(self.evaluator['supported_audio_formats'])
        
        # 验证音频文件 (仅在非评估模式下)
        if not self.evaluator.get('enabled', False) and self.audio_path:
            if not os.path.exists(self.audio_path):
                raise FileNotFoundError(f'音频文件不存在: {self.audio_path}')
            
            # 检查文件格式
            file_ext = os.path.splitext(self.audio_path)[1].lower()
            if file_ext not in self.supported_audio_formats:
                logger.warning(f'警告: 文件格式 {file_ext} 可能不被支持。支持的格式: {", ".join(self.supported_audio_formats)}')


def transcribe_audio(audio_path, model, language='zh', task='transcribe'):
    """使用 Whisper 转录音频"""
    logger.info('='*80)
    logger.info(f'开始转录: {os.path.basename(audio_path)}')
    logger.info('='*80)
    
    try:
        t_start = time.time()
        
        # 转录音频
        result = model.transcribe(
            audio_path,
            language=language,
            task=task,
            verbose=False,  # 不输出详细进度
            word_timestamps=True,  # 获取词级别时间戳
        )
        
        t_end = time.time()
        duration = t_end - t_start
        
        logger.info(f'✓ 转录完成,耗时: {duration:.2f}秒')
        logger.info('-'*80)
        
        # 完整转录文本
        full_text = result['text'].strip()
        logger.info(f'完整转录文本: {full_text}')
        logger.info('-'*80)
        
        # 检测到的语言
        detected_language = result.get('language', 'unknown')
        logger.info(f'检测到的语言: {detected_language}')
        
        # 分段信息
        segments = result.get('segments', [])
        logger.info(f'分段数量: {len(segments)}')
        logger.info('-'*80)
        
        # 输出每个分段的详细信息
        logger.info('分段详情:')
        for i, segment in enumerate(segments, 1):
            start = segment.get('start', 0)
            end = segment.get('end', 0)
            text = segment.get('text', '').strip()
            
            # 平均对数概率（置信度指标）
            avg_logprob = segment.get('avg_logprob', 0)
            # 无语音概率
            no_speech_prob = segment.get('no_speech_prob', 0)
            
            logger.info(f'\n  [{i}] 时间: {start:.2f}s - {end:.2f}s ({end-start:.2f}s)')
            logger.info(f'      文本: {text}')
            logger.info(f'      平均对数概率: {avg_logprob:.4f}')
            logger.info(f'      无语音概率: {no_speech_prob:.4f}')
            
            # 词级别时间戳
            words = segment.get('words', [])
            if words:
                logger.info(f'      词级别时间戳 ({len(words)}个词):')
                for word_info in words:
                    word = word_info.get('word', '')
                    word_start = word_info.get('start', 0)
                    word_end = word_info.get('end', 0)
                    word_prob = word_info.get('probability', 0)
                    logger.info(f'        - "{word}" [{word_start:.2f}s-{word_end:.2f}s] (prob: {word_prob:.3f})')
        
        logger.info('='*80)
        
        return {
            'text': full_text,
            'language': detected_language,
            'segments': segments,
            'duration': duration
        }
        
    except Exception as e:
        logger.error(f'✗ 转录失败: {e}')
        import traceback
        logger.error(traceback.format_exc())
        return None


def run_single_audio(config, model):
    """处理单个音频文件"""
    logger.info('\n' + '='*80)
    logger.info('单音频处理模式')
    logger.info('='*80)
    
    result = transcribe_audio(
        config.audio_path,
        model,
        language=config.language,
        task=config.task
    )
    
    if result:
        logger.info('\n处理完成!')
        logger.info(f'最终转录文本: {result["text"]}')
    else:
        logger.error('处理失败!')


def run_evaluator(config, model):
    """评估模式 - 批量处理音频文件"""
    logger.info('\n' + '='*80)
    logger.info('评估模式 - 批量处理')
    logger.info('='*80)
    
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
    total_duration = 0.0
    
    for i, audio_file in enumerate(audio_files, 1):
        audio_path = os.path.join(dataset_path, audio_file)
        logger.info(f'\n[{i}/{len(audio_files)}] 处理: {audio_file}')
        
        result = transcribe_audio(
            audio_path,
            model,
            language=config.language,
            task=config.task
        )
        
        if result:
            all_results.append({
                'audio_path': audio_path,
                'filename': audio_file,
                'transcription': result['text'],
                'language': result['language'],
                'segments': result['segments'],
                'duration': result['duration']
            })
            total_duration += result['duration']
        else:
            logger.warning(f'跳过失败的文件: {audio_file}')
    
    # 保存结果
    if all_results:
        evaluate_results(all_results, config, total_duration)
    else:
        logger.warning('没有成功处理的文件')


def evaluate_results(results, config, total_duration):
    """统计和保存评估结果"""
    logger.info('\n' + '='*80)
    logger.info('评估结果统计'.center(80))
    logger.info('='*80)
    
    total_files = len(results)
    logger.info(f'成功处理文件数: {total_files}')
    logger.info(f'总处理时间: {total_duration:.2f}秒')
    logger.info(f'平均处理时间: {total_duration/total_files:.2f}秒/文件')
    
    logger.info('\n' + '-'*80)
    logger.info('详细结果:')
    logger.info('-'*80)
    
    for i, result in enumerate(results, 1):
        logger.info(f'\n[{i}/{total_files}] {result["filename"]}')
        logger.info(f'  语言: {result["language"]}')
        logger.info(f'  耗时: {result["duration"]:.2f}秒')
        logger.info(f'  分段数: {len(result["segments"])}')
        logger.info(f'  转录: {result["transcription"]}')
    
    logger.info('\n' + '='*80)
    
    # 保存结果到 JSON
    results_path = config.evaluator.get('results_path', 'whisper_results.json')
    
    output_data = {
        'total_files': total_files,
        'total_duration': total_duration,
        'average_duration': total_duration / total_files if total_files > 0 else 0,
        'model': config.model_name,
        'language': config.language,
        'results': results
    }
    
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    logger.info(f'评估结果已保存到: {results_path}')
    logger.info('='*80)


def main():
    logger.info('='*80)
    logger.info('Whisper 语音识别系统'.center(80))
    logger.info('='*80)
    
    # 加载配置
    config = Config()
    
    # 加载 Whisper 模型
    logger.info(f'\n加载 Whisper 模型: {config.model_name}')
    logger.info('='*80)
    logger.info('提示: 首次使用会自动下载模型文件')
    logger.info('模型大小参考:')
    logger.info('  - tiny: ~39M (最快,准确度较低)')
    logger.info('  - base: ~74M (快速,准确度一般)')
    logger.info('  - small: ~244M (较慢,准确度较高)')
    logger.info('  - medium: ~769M (慢,准确度高)')
    logger.info('  - large: ~1550M (很慢,准确度最高)')
    logger.info('='*80)
    
    try:
        t_load_start = time.time()
        model = whisper.load_model(config.model_name)
        t_load_end = time.time()
        logger.info(f'✓ 模型加载完成,耗时: {t_load_end - t_load_start:.2f}秒')
    except Exception as e:
        logger.error(f'✗ 模型加载失败: {e}')
        sys.exit(1)
    
    # 根据模式运行
    if config.evaluator and config.evaluator.get('enabled', False):
        logger.info('\n评估模式已启用')
        run_evaluator(config, model)
    else:
        logger.info('\n单音频分析模式')
        run_single_audio(config, model)
    
    logger.info('\n' + '='*80)
    logger.info('程序结束')
    logger.info('='*80)


if __name__ == '__main__':
    main()
