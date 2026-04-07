"""Backend application package.

兼容仓库内同时存在的 `Backend.app.*` 与运行时 `app.*` 两套导入路径，
避免测试环境中出现重复模块身份或命名空间包混淆。
"""

import sys


sys.modules.setdefault("app", sys.modules[__name__])
