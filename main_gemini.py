"""
基于 Gemini 2.5 Pro/Flash 的视频理解系统
支持视频描述、问答、时间戳引用等功能
支持使用代理服务访问 Gemini API
"""

import os
import sys
import logging
import yaml
import json
import time
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('app_gemini.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class GeminiConfig:
    """Gemini 配置类"""
    config_path: str = './config_gemini.yml'
    GEMINI_API_KEY: str = ""
    
    # API 端点配置 (用于代理服务)
    api_base_url: Optional[str] = None  # 代理服务地址
    api_endpoint: str = "/models/{model}:generateContent"  # API 路径模板
    verify_ssl: bool = True  # 是否验证 SSL 证书 (代理服务可能需要设为 False)
    
    # 模型配置
    model: str = 'gemini-2.5-flash'  # 可选: gemini-2.5-flash, gemini-2.5-pro
    
    # 视频处理配置
    use_file_api: bool = True  # 是否使用 File API (推荐用于 >20MB 或 >1分钟的视频)
    video_fps: Optional[int] = None  # 自定义帧速率 (None=使用默认 1 FPS)
    video_start_offset: Optional[str] = None  # 开始时间偏移 (如 "10s", "1250s")
    video_end_offset: Optional[str] = None  # 结束时间偏移
    media_resolution: str = 'default'  # 'default' 或 'low' (低分辨率节省token)
    
    # YouTube 支持
    support_youtube: bool = False  # 是否支持 YouTube URL
    
    # 文件配置
    video_path: str = './input.mp4'
    prompt: str = '请用3句话总结这个视频。'
    
    # 评估器配置
    evaluator: Optional[Dict] = None
    
    # 支持的视频格式
    supported_video_formats: tuple = ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.m4v', '.3gpp', '.webm', '.mpeg', '.mpg')
    
    def _replace_file_placeholders(self, text: str) -> str:
        """替换文本中的 {{file_path}} 占位符为文件内容"""
        import re
        
        # 匹配 {{./path/to/file}} 或 {{path/to/file}}
        pattern = r'\{\{([^}]+)\}\}'
        
        def replace_match(match):
            file_path = match.group(1).strip()
            
            # 如果是相对路径，相对于配置文件所在目录
            if not os.path.isabs(file_path):
                config_dir = os.path.dirname(os.path.abspath(self.config_path))
                file_path = os.path.join(config_dir, file_path)
            
            # 读取文件内容
            try:
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    logger.info(f'✓ 已替换占位符: {match.group(0)} -> {file_path}')
                    return content
                else:
                    logger.warning(f'✗ 文件不存在: {file_path}，保留原占位符')
                    return match.group(0)
            except Exception as e:
                logger.error(f'✗ 读取文件失败 {file_path}: {e}，保留原占位符')
                return match.group(0)
        
        return re.sub(pattern, replace_match, text)
    
    def __post_init__(self):
        """从 YAML 文件加载配置"""
        if not os.path.exists(self.config_path):
            logger.warning(f'配置文件不存在: {self.config_path}, 将使用默认配置')
            return
            
        with open(self.config_path, 'r', encoding='utf-8') as yml_file:
            params = yaml.load(yml_file, Loader=yaml.FullLoader)
            logger.info(f'加载配置文件: {self.config_path}')
            
            self.GEMINI_API_KEY = params.get('GEMINI_API_KEY', self.GEMINI_API_KEY)
            self.api_base_url = params.get('api_base_url', self.api_base_url)
            self.api_endpoint = params.get('api_endpoint', self.api_endpoint)
            self.verify_ssl = params.get('verify_ssl', self.verify_ssl)
            self.model = params.get('model', self.model)
            self.use_file_api = params.get('use_file_api', self.use_file_api)
            self.video_fps = params.get('video_fps', self.video_fps)
            
            # 处理 video_start_offset 和 video_end_offset，支持数字自动转换为字符串
            start_offset = params.get('video_start_offset', self.video_start_offset)
            if isinstance(start_offset, (int, float)) and start_offset > 0:
                self.video_start_offset = f"{start_offset}s"
            elif start_offset:
                self.video_start_offset = start_offset
            
            end_offset = params.get('video_end_offset', self.video_end_offset)
            if isinstance(end_offset, (int, float)) and end_offset > 0:
                self.video_end_offset = f"{end_offset}s"
            elif end_offset:
                self.video_end_offset = end_offset
            
            self.media_resolution = params.get('media_resolution', self.media_resolution)
            self.support_youtube = params.get('support_youtube', self.support_youtube)
            self.video_path = params.get('video_path', self.video_path)
            self.prompt = params.get('prompt', self.prompt)
            self.evaluator = params.get('evaluator', {'enabled': False})
            
            # 替换 prompt 中的 {{file_path}} 为文件内容
            self.prompt = self._replace_file_placeholders(self.prompt)
        
        # 验证 API Key
        if not self.GEMINI_API_KEY:
            raise ValueError('GEMINI_API_KEY 未设置! 请在配置文件中设置 API Key')
        
        # 验证视频文件 (非评估模式)
        if not self.evaluator.get('enabled', False):
            if self.support_youtube and self.video_path.startswith('http'):
                logger.info(f'使用 YouTube 视频: {self.video_path}')
            elif not os.path.exists(self.video_path):
                raise FileNotFoundError(f'视频文件不存在: {self.video_path}')
            else:
                file_ext = os.path.splitext(self.video_path)[1].lower()
                if file_ext not in self.supported_video_formats:
                    logger.warning(f'文件格式 {file_ext} 可能不被支持')


class GeminiVideoProcessor:
    """Gemini 视频处理器"""
    
    def __init__(self, config: GeminiConfig):
        self.config = config
        
        if not GENAI_AVAILABLE:
            raise ImportError("请先安装 google-genai: uv add google-genai")
        
        # 构建客户端参数
        client_kwargs = {'api_key': config.GEMINI_API_KEY}
        
        # 如果配置了自定义 API 基础URL
        if config.api_base_url:
            logger.info(f'使用自定义 API 端点: {config.api_base_url}{config.api_endpoint}')
            logger.warning('⚠️  使用自定义 API 端点')
            
            # 尝试设置 base_url 和 SSL 验证
            try:
                import httpx
                
                # 如果禁用 SSL 验证
                if not config.verify_ssl:
                    logger.warning('⚠️  已禁用 SSL 证书验证 (不推荐用于生产环境)')
                    http_client = httpx.Client(
                        base_url=config.api_base_url,
                        verify=False,  # 禁用 SSL 验证
                        timeout=60.0
                    )
                    # 使用 httpxClient 参数 (注意大小写)
                    client_kwargs['http_options'] = types.HttpOptions(
                        base_url=config.api_base_url,
                        httpxClient=http_client
                    )
                else:
                    client_kwargs['http_options'] = types.HttpOptions(
                        base_url=config.api_base_url
                    )
                    
            except Exception as e:
                logger.warning(f'设置自定义端点失败: {e}')
                logger.info('尝试使用环境变量: GOOGLE_API_BASE')
        
        self.client = genai.Client(**client_kwargs)
        logger.info(f'✓ 已初始化 Gemini 客户端 (模型: {config.model})')
    
    def _is_youtube_url(self, path: str) -> bool:
        """检查是否为 YouTube URL"""
        return path.startswith('http') and ('youtube.com' in path or 'youtu.be' in path)
    
    def _upload_video_file(self, video_path: str) -> Any:
        """使用 File API 上传视频文件"""
        import tempfile
        import shutil
        
        logger.info(f'[File API] 正在上传视频: {video_path}')
        
        # 检查路径是否包含非 ASCII 字符
        try:
            video_path.encode('ascii')
            upload_path = video_path
            temp_file = None
        except UnicodeEncodeError:
            # 路径包含中文，复制到临时文件
            logger.info('检测到中文路径，创建临时文件...')
            file_ext = os.path.splitext(video_path)[1]
            with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as tmp:
                temp_file = tmp.name
            shutil.copy2(video_path, temp_file)
            upload_path = temp_file
            logger.info(f'临时文件: {temp_file}')
        
        try:
            # 上传文件
            myfile = self.client.files.upload(file=upload_path)
            logger.info(f'✓ 视频上传成功: {myfile.name}')
            
            # 等待文件处理完成
            logger.info('等待文件处理...')
            while myfile.state.name == 'PROCESSING':
                time.sleep(1)
                myfile = self.client.files.get(name=myfile.name)
            
            if myfile.state.name == 'FAILED':
                raise ValueError(f'文件处理失败: {myfile.state}')
            
            logger.info(f'✓ 文件处理完成: {myfile.state.name}')
            return myfile
            
        except Exception as e:
            logger.error(f'✗ 文件上传失败: {e}')
            raise
        finally:
            # 清理临时文件
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    logger.info('✓ 临时文件已清理')
                except Exception as e:
                    logger.warning(f'临时文件清理失败: {e}')
    
    def _read_video_bytes(self, video_path: str) -> bytes:
        """读取视频文件为字节流 (用于内嵌方式)，自动抽帧降分辨率"""
        import tempfile
        import subprocess
        
        logger.info(f'读取视频文件: {video_path}')
        # 生成临时小视频（5fps, 320x240）
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
            tmp_video_path = tmp.name
        
        ffmpeg_cmd = [
            'ffmpeg',
            '-y',  # 覆盖输出
            '-i', video_path,
            "-vf", "select='eq(pict_type,PICT_TYPE_I)',scale=320:240",
            '-vsync', 'vfr',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '32',
            '-an',  # 去除音频
            tmp_video_path
        ]
        logger.info(f'使用 ffmpeg 只抽关键帧并降分辨率: {" ".join(ffmpeg_cmd)}')
        try:
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            logger.error(f'ffmpeg 处理失败: {e}')
            # 失败则回退为原视频
            tmp_video_path = video_path
        
        file_size = os.path.getsize(tmp_video_path)
        size_mb = file_size / (1024 * 1024)
        if size_mb > 20:
            logger.warning(f'处理后视频仍较大 ({size_mb:.2f} MB), 建议使用 File API (use_file_api=True)')
        with open(tmp_video_path, 'rb') as f:
            video_bytes = f.read()
        logger.info(f'✓ 视频读取完成: {size_mb:.2f} MB')
        # 删除临时文件（如果不是原视频）
        if tmp_video_path != video_path:
            try:
                os.remove(tmp_video_path)
            except Exception as e:
                logger.warning(f'临时文件删除失败: {e}')
        return video_bytes
    
    def _build_video_metadata(self) -> Optional[types.VideoMetadata]:
        """构建视频元数据 (用于自定义处理)"""
        metadata_params = {}
        
        # 设置剪辑间隔
        if self.config.video_start_offset:
            metadata_params['start_offset'] = self.config.video_start_offset
        if self.config.video_end_offset:
            metadata_params['end_offset'] = self.config.video_end_offset
        
        # 设置自定义帧速率
        if self.config.video_fps is not None:
            metadata_params['fps'] = self.config.video_fps
        
        if metadata_params:
            logger.info(f'使用自定义视频处理参数: {metadata_params}')
            return types.VideoMetadata(**metadata_params)
        
        return None
    
    def _get_mime_type(self, video_path: str) -> str:
        """根据文件扩展名获取 MIME 类型"""
        ext = os.path.splitext(video_path)[1].lower()
        mime_types = {
            '.mp4': 'video/mp4',
            '.mov': 'video/mov',
            '.avi': 'video/avi',
            '.mkv': 'video/x-matroska',
            '.flv': 'video/x-flv',
            '.wmv': 'video/wmv',
            '.m4v': 'video/mp4',
            '.3gpp': 'video/3gpp',
            '.webm': 'video/webm',
            '.mpeg': 'video/mpeg',
            '.mpg': 'video/mpg'
        }
        return mime_types.get(ext, 'video/mp4')
    
    def process_video(self, video_path: str, prompt: str) -> tuple[str, Dict]:
        """
        处理视频并生成回答
        
        - use_file_api=False（内嵌模式）时，会自动用 ffmpeg 抽帧（5fps）和降分辨率（320x240），再传递给 Gemini。
        
        Returns:
            (response_text, timings)
        """
        logger.info(f'\n{"="*60}')
        logger.info(f'开始处理视频: {os.path.basename(video_path)}')
        logger.info(f'{"="*60}')
        
        timings = {}
        t_start = time.time()
        
        try:
            # 构建请求内容
            parts = []
            video_metadata = self._build_video_metadata()
            
            # 方式1: YouTube URL
            if self.config.support_youtube and self._is_youtube_url(video_path):
                logger.info('[方式] 使用 YouTube URL')
                part = types.Part(
                    file_data=types.FileData(file_uri=video_path)
                )
                if video_metadata:
                    part.video_metadata = video_metadata
                parts.append(part)
            
            # 方式2: File API (推荐用于大文件)
            elif self.config.use_file_api:
                logger.info('[方式] 使用 File API 上传')
                t_upload_start = time.time()
                myfile = self._upload_video_file(video_path)
                t_upload_end = time.time()
                timings['upload_time'] = t_upload_end - t_upload_start
                
                # 使用上传的文件引用
                parts.append(myfile)
            
            # 方式3: 内嵌视频数据 (适用于小文件 <20MB)
            else:
                logger.info('[方式] 使用内嵌视频数据')
                video_bytes = self._read_video_bytes(video_path)
                mime_type = self._get_mime_type(video_path)
                
                part = types.Part(
                    inline_data=types.Blob(
                        data=video_bytes,
                        mime_type=mime_type
                    )
                )
                if video_metadata:
                    part.video_metadata = video_metadata
                parts.append(part)
            
            # 添加提示词
            parts.append(types.Part(text=prompt))
            
            # 发送请求
            logger.info(f'\n[提示词] {prompt}')
            logger.info('\n正在生成回答...\n')
            
            t_request_start = time.time()
            
            # 构建生成配置 (如需要可以添加其他参数)
            if self.config.media_resolution == 'low':
                logger.info('使用低媒体分辨率 (节省 token)')
            
            response = self.client.models.generate_content(
                model=self.config.model,
                contents=types.Content(parts=parts)
            )
            
            t_request_end = time.time()
            timings['request_time'] = t_request_end - t_request_start
            timings['total_time'] = t_request_end - t_start
            
            # 提取响应文本
            response_text = response.text
            
            logger.info(f'\n{"="*60}')
            logger.info('[AI 回答]')
            logger.info(f'{"="*60}')
            print(response_text)
            logger.info(f'\n{"="*60}')
            
            # 输出性能指标
            logger.info('[性能指标]')
            if 'upload_time' in timings:
                logger.info(f'  - 上传耗时: {timings["upload_time"]:.3f}s')
            logger.info(f'  - 请求耗时: {timings["request_time"]:.3f}s')
            logger.info(f'  - 总耗时: {timings["total_time"]:.3f}s')
            logger.info(f'{"="*60}\n')
            
            return response_text, timings
            
        except Exception as e:
            logger.error(f'✗ 处理失败: {e}')
            import traceback
            traceback.print_exc()
            return None, timings


def extract_label_from_filename(filename: str) -> str:
    """从文件名提取真值标签"""
    true_labels = ("画画", "做手工", "过家家", "运动")
    for label in true_labels:
        if label in filename:
            return label
    return ""


def evaluate_results(results: List[Dict], config: GeminiConfig):
    """评估结果并计算准确率"""
    logger.info(f"\n{'='*60}")
    logger.info("开始评估结果".center(60))
    logger.info(f"{'='*60}")
    
    correct_predictions = 0
    total_files = len(results)
    
    if total_files == 0:
        logger.warning("没有找到评估结果")
        return
    
    # 分类统计
    class_stats = {}
    
    for result in results:
        video_path = result['video_path']
        prediction_text = result['prediction']
        
        # 提取真值标签
        filename = os.path.basename(video_path)
        true_label = extract_label_from_filename(filename)
        
        if true_label not in class_stats:
            class_stats[true_label] = {'total': 0, 'correct': 0}
        class_stats[true_label]['total'] += 1
        
        try:
            # 尝试解析 JSON 格式的回答
            prediction_data = json.loads(prediction_text)
            predicted_label = prediction_data.get('activity_label', '')
            
            is_correct = (predicted_label == true_label)
            if is_correct:
                correct_predictions += 1
                class_stats[true_label]['correct'] += 1
            
            logger.info(f"文件: {filename}")
            logger.info(f"  - 真值: {true_label}")
            logger.info(f"  - 预测: {predicted_label}")
            logger.info(f"  - 结果: {'✓ 正确' if is_correct else '✗ 错误'}")
            logger.info(f"  - 描述: {prediction_data.get('content_description', 'N/A')[:100]}...")
            logger.info("-" * 20)
            
        except json.JSONDecodeError:
            logger.error(f"文件: {filename} - 无法解析 JSON: {prediction_text[:200]}...")
    
    # 计算准确率
    accuracy = (correct_predictions / total_files) * 100 if total_files > 0 else 0
    
    logger.info(f"\n{'='*60}")
    logger.info("评估摘要".center(60))
    logger.info(f"总文件数: {total_files}")
    logger.info(f"正确预测数: {correct_predictions}")
    logger.info(f"准确率: {accuracy:.2f}%")
    
    # 每类准确率
    logger.info('\n每类准确率:'.center(60))
    per_class_results = {}
    for label, stats in class_stats.items():
        total = stats['total']
        correct = stats['correct']
        acc = (correct / total) * 100 if total > 0 else 0
        logger.info(f"  - {label}: {correct}/{total} => {acc:.2f}%")
        per_class_results[label] = {
            'total': total,
            'correct': correct,
            'accuracy': round(acc, 2)
        }
    
    logger.info(f"{'='*60}")
    
    # 保存结果
    results_path = config.evaluator.get('results_path', 'eval_results_gemini.json')
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump({
            'accuracy': accuracy,
            'total_files': total_files,
            'correct_predictions': correct_predictions,
            'per_class': per_class_results,
            'results': results
        }, f, ensure_ascii=False, indent=4)
    
    logger.info(f"评估结果已保存到: {results_path}")


def run_evaluator(config: GeminiConfig):
    """运行评估器"""
    dataset_path = config.evaluator.get('dataset_path')
    if not dataset_path or not os.path.isdir(dataset_path):
        logger.error(f"数据集路径无效: {dataset_path}")
        return
    
    # 获取所有视频文件
    video_files = [
        f for f in os.listdir(dataset_path)
        if os.path.splitext(f)[1].lower() in config.supported_video_formats
    ]
    
    logger.info(f"在 {dataset_path} 中找到 {len(video_files)} 个视频文件")
    
    processor = GeminiVideoProcessor(config)
    all_results = []
    timing_aggregates = {
        'upload_time': 0.0,
        'request_time': 0.0,
        'total_time': 0.0
    }
    
    for i, video_file in enumerate(video_files, 1):
        video_path = os.path.join(dataset_path, video_file)
        
        logger.info(f"\n[{i}/{len(video_files)}] 处理: {video_file}")
        
        # 处理视频
        prediction, timings = processor.process_video(video_path, config.prompt)
        
        if prediction:
            all_results.append({
                'video_path': video_path,
                'prediction': prediction,
                'timings': timings
            })
            
            # 累计耗时
            for key in timing_aggregates:
                timing_aggregates[key] += timings.get(key, 0.0)
        
        # 短暂休息,避免 API 限流
        if i < len(video_files):
            time.sleep(1)
    
    # 评估结果
    if all_results:
        evaluate_results(all_results, config)
        
        # 输出总体耗时
        total_videos = len(all_results)
        logger.info(f'\n{"="*60}')
        logger.info('耗时统计汇总'.center(60))
        logger.info(f"处理视频数量: {total_videos}")
        if total_videos > 0:
            if timing_aggregates['upload_time'] > 0:
                logger.info(f"总上传耗时: {timing_aggregates['upload_time']:.3f}s "
                          f"(平均 {timing_aggregates['upload_time']/total_videos:.3f}s/视频)")
            logger.info(f"总请求耗时: {timing_aggregates['request_time']:.3f}s "
                       f"(平均 {timing_aggregates['request_time']/total_videos:.3f}s/视频)")
            logger.info(f"总耗时: {timing_aggregates['total_time']:.3f}s "
                       f"(平均 {timing_aggregates['total_time']/total_videos:.3f}s/视频)")
        logger.info(f'{"="*60}')


def run_single_video(config: GeminiConfig):
    """处理单个视频"""
    logger.info(f'\n{"="*60}')
    logger.info('Gemini 视频理解系统'.center(60))
    logger.info(f'{"="*60}')
    logger.info(f'  - 模型: {config.model}')
    logger.info(f'  - 视频: {config.video_path}')
    logger.info(f'  - 提示词: {config.prompt}')
    logger.info(f'{"="*60}\n')
    
    processor = GeminiVideoProcessor(config)
    response, timings = processor.process_video(config.video_path, config.prompt)
    
    if response:
        logger.info('✓ 处理完成')
    else:
        logger.error('✗ 处理失败')


def main():
    """主函数"""
    try:
        config = GeminiConfig()
        
        if config.evaluator and config.evaluator.get('enabled', False):
            logger.info("评估模式已启用")
            run_evaluator(config)
        else:
            logger.info("单视频分析模式")
            run_single_video(config)
            
    except Exception as e:
        logger.error(f'程序异常: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
