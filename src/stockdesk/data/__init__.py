"""[DATA] 数据网关：唯一访问外部数据的模块。

两种进数方式，写出的快照格式完全一样：
- fetch：Mac 上直连来源（雅虎、SEC、披露易、FRED、stockanalysis、AKShare）
- import：云端由 Claude 用 WebFetch 抓好网页、存成 JSON 后导入
doctor 做网络预检，判断现在是云端还是 Mac、哪些来源连得上。
"""

from .doctor import doctor, environment, load_network_profile
from .fetch import fetch
from .importer import ack_gaps, import_json
from .sources import load_sources
from .store import data_root

__all__ = [
    "ack_gaps", "data_root", "doctor", "environment", "fetch", "import_json", "load_network_profile", "load_sources",
]
