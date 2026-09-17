"""Entry point for sukoon-server.exe — the boot task that serves every till (ADR-0035 §1).

An installed copy is always the production configuration; a developer can still override it.
"""
import os
import sys

os.environ.setdefault("SUKOON_CONFIG", "production")

from sukoon.run import main  # noqa: E402

sys.exit(main())
