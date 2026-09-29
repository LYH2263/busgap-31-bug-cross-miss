import os

# 必须在导入 app.* 之前：app.database 会按 settings.database_url 立即建引擎
os.environ.setdefault("DATABASE_URL", "sqlite://")
