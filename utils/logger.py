import logging
import sys
from datetime import datetime
from pathlib import Path


_logger: logging.Logger | None = None


def setup_logger(
    name: str = "arc-agi-3",
    level: str = "INFO",
    results_dir: str = "results",
    to_file: bool = True,
) -> logging.Logger:
    """실험용 로거를 설정합니다."""
    global _logger

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 콘솔 핸들러
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # 파일 핸들러
    if to_file:
        log_dir = Path(results_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fh = logging.FileHandler(log_dir / f"experiment_{ts}.log")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    _logger = logger
    return logger


def get_logger() -> logging.Logger:
    """현재 로거를 반환합니다. 없으면 기본 설정으로 생성합니다."""
    global _logger
    if _logger is None:
        _logger = setup_logger()
    return _logger
