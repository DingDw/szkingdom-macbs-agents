#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KDOP 通用访问客户端（kdop-core）
================================

从具体项目里抽出来的通用层：只负责「认证 / 传输 / 通用查询 / 追溯」四件事，
不绑定任何项目、版本、仓库。

分层
----
1. 认证层  ``ensure_session``：无头浏览器登录一次 → 缓存 Bearer token + Cookie；
            token 过期或服务端踢人时静默重登，调用方无感。
2. 传输层  ``api`` / ``call``：任意网关接口的 POST/GET 表单调用，自动续期、
            自动识别「返回登录页 HTML」这类伪成功。
3. 业务层  ``list_projects`` / ``list_versions`` / ``search_issues`` /
            ``requirements`` / ``issue_detail`` / ``search_commits``：封装
            KDOP 的通用概念（项目、版本、需求、缺陷、提交）。
4. 追溯层  ``trace_version``：版本 → 需求清单 → 每个需求的提交证据，
            证据来自两个独立通道（KDOP 全局代码检索 + 本地 git 提交信息检索）。

常用命令::

    kdop_core.py config set --base-url http://jzdevops.szkingdom.com:8080 \\
                            --username <工号> --password <密码>
    kdop_core.py login
    kdop_core.py versions --match "1\\.7\\.9"
    kdop_core.py requirements --version FS2.5_macbs_1.7.9.0 --format md
    kdop_core.py commits --keyword FS-CBS-24123
    kdop_core.py trace --version FS2.5_macbs_1.7.9.0 --out trace.json --format md
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

# ── 路径与全局常量 ────────────────────────────────────────────────────────
KDOP_HOME = Path(os.environ.get("KDOP_HOME") or (Path.home() / ".kdop"))
CONFIG_PATH = KDOP_HOME / "config.json"
SESSION_PATH = KDOP_HOME / "session.json"
LOG_PATH = KDOP_HOME / "kdop.log"

SESSION_VERSION = 2

# 默认指向金证内网 KDOP；换部署用 config set --base-url 或 KDOP_BASE_URL 覆盖。
DEFAULT_BASE_URL = "http://jzdevops.szkingdom.com:8080"

# 网关接口清单：全部可通过 config.endpoints 覆盖，接口变更时不用改代码。
DEFAULT_ENDPOINTS: Dict[str, str] = {
    "login_page": "/login.html",
    "user_info": "/gateway/core/core/user/security/getLoginUserInfo",
    "version_list": "/gateway/issue/issue/issue/getIssueVersionList",
    "issue_search": "/gateway/issue/issue/issue/searchIssue",
    # 需求详情：不同版本部署路径可能不同，取不到时自动退回 searchIssue 单条查询。
    "issue_detail": "/gateway/issue/issue/issue/getIssueDetail",
    # 当前账号有权限的产品/项目目录（平台顶栏项目切换器用的就是这个接口）
    "project_list": "/gateway/core/core/product/catalog/getPermitProductAndProjectCatalog",
    # 全局检索：module=1 需求 / 2 缺陷 / 3 用例 / 4 代码提交
    "global_search": "/gateway/core/core/global/search/listResult",
}

# 全局检索的模块号（来自平台前端 index/src/global-search.js）
GLOBAL_SEARCH_MODULES = {"story": 1, "bug": 2, "case": 3, "commit": 4}
# searchIssue 的应用号（1=需求/工作项 2=缺陷）
APP_IDS = {"story": 1, "bug": 2}

# 需求（故事）字段清单：field 参数必须显式列举，custom_* 通配在新版接口不稳定。
STORY_FIELDS = (
    "id,issueNum,parentId,parentIdName,issueTypeName,title,versionId,versionIdName,"
    "assigneeName,developersName,testerName,status,statusName,priorityName,moduleName,"
    "productModuleName,brokerNameName,newIssueFlag,newIssueFlagName,storyPoints,"
    "createDate,updateDate,resolutionTime,closeDate,developCompletionTime,"
    "updateUserName,updaterName,modifyUserName,lastModifiedByName,"
    "custom_75,custom_75Name,custom_86,custom_87,custom_88,custom_88Name,custom_191,"
    "custom_469,custom_586,custom_589,custom_802,custom_802Name"
)
DEFECT_FIELDS = (
    "id,issueNum,parentId,parentIdName,issueTypeName,title,versionId,versionIdName,"
    "assigneeName,developerForBugName,reporterName,status,statusName,priorityName,"
    "bugGradesName,moduleName,productModule,productModuleName,bugTypeName,bugRootSource,"
    "createDate,updateDate,closeDate,bugFixTime,repairTime,dueDate,plannedFinishDate,"
    "customPlanDate,customDesireDate,timeoriginalestimate,timeestimate,timespent,"
    "custom_129Name,custom_130Name,custom_132,custom_133,custom_135,custom_137Name,"
    "custom_138,custom_138Name,custom_142,custom_142Name,custom_145Name,custom_491,"
    "custom_503Name,custom_802,custom_802Name"
)

# 状态口径（与清算工作台/周报一致，可按团队习惯在 config 里覆盖）
STORY_DEV_DONE = {"待测试", "测试中", "已解决", "已关闭"}
STORY_TEST_DONE = {"已解决", "已关闭"}
DEFECT_FIXED = {"修复", "拒绝修复", "关闭", "丢弃"}
DEFECT_CLOSED = {"关闭", "丢弃"}

# 需求编号规则：FS-CBS-24123。提交信息里出现编号即视为弱关联证据。
REQ_NO_RE = re.compile(r"FS-CBS-\d+", re.I)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

CHROME_CANDIDATES = [
    os.environ.get("KDOP_CHROME", ""),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]

# 网关鉴权失效的典型提示（返回 JSON 而非 HTML 的情况）
AUTH_FAILURE_HINTS = (
    "登录超时",
    "重新登录",
    "登录失效",
    "未登录",
    "请先登录",
    "登录状态",
    "token",
    "未授权",
    "无权限访问",
)


class KdopError(RuntimeError):
    """KDOP 访问异常（接口/网络/参数）"""


class KdopAuthError(KdopError):
    """登录失败 / 凭据无效"""


class KdopConfigError(KdopError):
    """缺少必要配置"""


class _SessionExpired(KdopError):
    """本地登录态失效，需要重新登录"""


# ══════════════════════════════════════════════════════════════════════════
# 配置与会话持久化
# ══════════════════════════════════════════════════════════════════════════
def load_config(required: bool = True) -> Dict[str, Any]:
    """读取配置：环境变量 > ~/.kdop/config.json > 默认值。"""
    raw: Dict[str, Any] = {}
    if CONFIG_PATH.exists():
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise KdopConfigError(f"配置文件损坏：{CONFIG_PATH}（{exc}）") from exc

    base_url = os.environ.get("KDOP_BASE_URL") or raw.get("base_url") or DEFAULT_BASE_URL
    username = os.environ.get("KDOP_USERNAME") or raw.get("username")
    password = os.environ.get("KDOP_PASSWORD") or raw.get("password")
    project_id = os.environ.get("KDOP_PROJECT_ID") or raw.get("project_id")

    endpoints = dict(DEFAULT_ENDPOINTS)
    endpoints.update({k: v for k, v in (raw.get("endpoints") or {}).items() if v})

    if required and not (username and password):
        raise KdopConfigError(
            "尚未配置 KDOP 账号，请先执行：\n"
            f'  python "{Path(__file__).resolve()}" config set '
            "--username <工号> --password <密码>\n"
            "或用环境变量 KDOP_USERNAME / KDOP_PASSWORD 提供。"
        )

    return {
        "base_url": str(base_url).rstrip("/"),
        "username": username,
        "password": password,
        "project_id": project_id,
        "endpoints": endpoints,
        "repos": list(raw.get("repos") or []),
        "headless": bool(raw.get("headless", True)),
    }


def save_config(cfg: Dict[str, Any]) -> Path:
    """落盘配置（权限 600；Windows 上 chmod 无效，属本机信任模型）。"""
    KDOP_HOME.mkdir(parents=True, exist_ok=True)
    payload = {k: v for k, v in cfg.items() if v not in (None, "", [], {})}
    CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except Exception:
        pass
    return CONFIG_PATH


def update_config(**patch: Any) -> Path:
    """局部更新配置，不清掉用户已有的其他键（例如端点覆盖、仓库清单）。"""
    current: Dict[str, Any] = {}
    if CONFIG_PATH.exists():
        try:
            current = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            current = {}
    for key, value in patch.items():
        if value is None:
            continue
        if key == "endpoints":
            merged = dict(current.get("endpoints") or {})
            merged.update(value)
            current["endpoints"] = merged
        else:
            current[key] = value
    return save_config(current)


def log(msg: str) -> None:
    try:
        KDOP_HOME.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:
        pass


def _jwt_exp(token: str) -> int:
    """只解析 JWT 的 exp（不验签），用于判断本地 token 是否还能用。"""
    try:
        segments = token.split("Bearer-", 1)[-1].split(".")
        if len(segments) < 2:
            return 0
        raw = segments[1]
        raw += "=" * (-len(raw) % 4)
        return int(json.loads(base64.urlsafe_b64decode(raw)).get("exp") or 0)
    except Exception:
        return 0


def load_session(cfg: Dict[str, Any], min_ttl: int = 120) -> Optional[Dict[str, Any]]:
    """读取本地登录态；绑定了 base_url + 账号，换环境自动失效。"""
    if not SESSION_PATH.exists():
        return None
    try:
        data = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    if data.get("v") != SESSION_VERSION:
        return None
    if data.get("base_url") != cfg["base_url"] or str(data.get("username")) != str(cfg.get("username")):
        return None
    if not data.get("token"):
        return None
    if int(data.get("expires_at") or 0) - min_ttl < time.time():
        return None
    return data


def save_session(data: Dict[str, Any]) -> None:
    KDOP_HOME.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(SESSION_PATH, 0o600)
    except Exception:
        pass


def _detect_browser() -> Optional[str]:
    for path in CHROME_CANDIDATES:
        if path and Path(path).exists():
            return path
    return None


def normalize_path(path: str) -> str:
    """接口路径归一化。

    Git Bash / MSYS 会把以 `/` 开头的参数当成本地路径转换
    （`/gateway/x` → `C:/.../PortableGit/gateway/x`），这里统一还原。
    同时兼容平台前端的 `serviceId-core/xxx` 写法。
    """
    p = str(path or "").replace("\\", "/").strip()
    if "gateway/" in p and not p.startswith("/gateway/"):
        p = p[p.index("gateway/"):]
    # 平台前端两种写法：`serviceId-core/xxx` 与 `service-core/xxx`，都映射到 gateway/<svc>/<svc>/xxx
    match = re.match(r"^/?service(?:[iI][dD])?-(\w+)/(.+)$", p)
    if match:
        service, rest = match.group(1), match.group(2)
        p = f"/gateway/{service}/{service}/{rest}"
    if not p.startswith("/"):
        p = "/" + p
    return p


# ══════════════════════════════════════════════════════════════════════════
# 通用 KDOP 客户端
# ══════════════════════════════════════════════════════════════════════════
class KdopClient:
    """KDOP 会话对象，实现「认证 + 传输 + 通用业务方法」。

    用法::

        with KdopClient() as client:
            issues = client.requirements(["FS2.5_macbs_1.7.9.0"])
            commits = client.search_commits("FS-CBS-24123")
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        project_id: Optional[str] = None,
        headless: bool = True,
        verbose: bool = True,
        timeout: int = 60,
        keep_browser: bool = False,
    ) -> None:
        self.cfg = config or load_config()
        self.base_url: str = self.cfg["base_url"]
        self.username: str = str(self.cfg.get("username") or "")
        self.password: str = str(self.cfg.get("password") or "")
        self.project_id: Optional[str] = project_id or self.cfg.get("project_id")
        self.endpoints: Dict[str, str] = dict(self.cfg.get("endpoints") or DEFAULT_ENDPOINTS)
        self.repos: List[str] = list(self.cfg.get("repos") or [])
        self.headless = headless
        self.verbose = verbose
        self.timeout = timeout
        self.keep_browser = keep_browser

        self.token: Optional[str] = None
        self.cookies: List[Dict[str, Any]] = []
        self.user: Dict[str, Any] = {}
        self.expires_at: int = 0
        self._last_save: float = 0.0
        self.session_source = "none"  # none / cache / fresh
        self._pw = None
        self.browser = None
        self.context = None
        self.page = None

    # ── 生命周期 ────────────────────────────────────────────────────────
    def __enter__(self) -> "KdopClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _info(self, msg: str) -> None:
        if self.verbose:
            print(f"[kdop] {msg}", file=sys.stderr)

    def close(self) -> None:
        for obj in (self.context, self.browser):
            try:
                if obj:
                    obj.close()
            except Exception:
                pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self.context = self.browser = self.page = self._pw = None

    # ── 认证层 ──────────────────────────────────────────────────────────
    def ensure_session(self, force: bool = False) -> Dict[str, Any]:
        """保证有可用登录态：优先本地缓存（不起浏览器），失效才无头登录。"""
        if not force:
            cached = load_session(self.cfg)
            if cached:
                self.token = cached["token"]
                self.cookies = cached.get("cookies") or []
                self.user = cached.get("user") or {}
                self.expires_at = int(cached.get("expires_at") or 0)
                self.session_source = "cache"
                self._info(
                    f"复用本地登录态（{self.user.get('userName') or self.username}，"
                    f"有效至 {datetime.fromtimestamp(int(cached['expires_at'])):%Y-%m-%d %H:%M}）"
                )
                return self.user
        self.browser_login()
        return self.user

    def browser_login(self) -> Dict[str, Any]:
        """无头浏览器登录：填表 → 点登录 → 抓 token/Cookie → 立刻关浏览器。"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise KdopConfigError(
                "缺少 playwright，无法执行登录。请先运行 scripts/install.ps1"
                "（Windows）或 scripts/install.sh（macOS/Linux）。"
            ) from exc

        self._info(f"无头登录 {self.base_url}，账号 {self.username}")
        self._pw = sync_playwright().start()
        launch_kwargs: Dict[str, Any] = {
            "headless": self.headless,
            "args": ["--no-sandbox", "--disable-setuid-sandbox"],
        }
        browser_path = _detect_browser()
        if browser_path:
            launch_kwargs["executable_path"] = browser_path
        try:
            self.browser = self._pw.chromium.launch(**launch_kwargs)
            self.context = self.browser.new_context(user_agent=UA, viewport={"width": 1440, "height": 900})
            self.context.set_default_timeout(60000)
            self.page = self.context.new_page()
            user = self._login_flow()
            self._capture_session(user)
            return user
        finally:
            if not self.keep_browser:
                self.close()

    def _login_flow(self, attempts: int = 3) -> Dict[str, Any]:
        last: Optional[Exception] = None
        for i in range(1, attempts + 1):
            try:
                return self._login_once()
            except KdopAuthError as exc:
                last = exc
                self._info(f"第 {i}/{attempts} 次登录失败：{exc}")
                time.sleep(2)
        raise KdopAuthError(f"自动登录失败（已重试 {attempts} 次）：{last}")

    def _login_once(self) -> Dict[str, Any]:
        page = self.page
        page.goto(f"{self.base_url}{self.endpoints['login_page']}", wait_until="domcontentloaded")
        try:
            page.wait_for_selector("#loginName", timeout=20000)
        except Exception as exc:
            raise KdopAuthError(
                f"登录页打不开或结构变化（{self.base_url}{self.endpoints['login_page']}），"
                "请确认地址可达、网络无代理拦截"
            ) from exc

        time.sleep(0.8)
        page.fill("#loginName", self.username)
        page.fill("#loginPassword", self.password)

        code = self._maybe_captcha()
        if code:
            try:
                page.fill("#validateCode", code)
            except Exception:
                pass

        self._click_login()
        time.sleep(4)

        user = self._page_user_info()
        if not user:
            raise KdopAuthError("提交登录后未取得登录态：账号或密码可能不正确，或验证码未通过")
        self._info(f"登录成功：{user.get('userName')}（{user.get('userId')}）")
        log(f"login ok user={self.username} name={user.get('userName')}")
        return user

    def _click_login(self) -> None:
        for sel in ("#loginButton", ".login-btn", "button[type=submit]", "a.login-btn", "text=登录"):
            try:
                el = self.page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    return
            except Exception:
                continue
        try:
            self.page.keyboard.press("Enter")
        except Exception as exc:
            raise KdopAuthError("未能点击登录按钮") from exc

    # ── 图形验证码（可选能力） ──────────────────────────────────────────
    def _captcha_visible(self) -> bool:
        try:
            div = self.page.query_selector("#validateCodeDiv")
            if div:
                display = div.evaluate("el => getComputedStyle(el).display")
                if display and display != "none":
                    return True
            img = self.page.query_selector("#validImg")
            return bool(img and img.is_visible())
        except Exception:
            return False

    def _maybe_captcha(self) -> Optional[str]:
        if not self._captcha_visible():
            return None
        guess = self._solve_captcha()
        if guess:
            return guess
        custom = os.environ.get("KDOP_CAPTCHA_CMD")
        if custom:
            try:
                out = subprocess.run(custom, shell=True, capture_output=True, text=True, timeout=30)
                guess = (out.stdout or "").strip()
                if guess:
                    self._info(f"外部 OCR 返回验证码：{guess}")
                    return guess
            except Exception as exc:
                self._info(f"外部 OCR 调用失败：{exc}")
        raise KdopAuthError(
            "登录页要求图形验证码，本机缺少 OCR 依赖。可选方案：\n"
            "  1) pip install pytesseract pillow 并安装 Tesseract-OCR；\n"
            "  2) 设置环境变量 KDOP_CAPTCHA_CMD 指向识别脚本（stdout 输出验证码）；\n"
            "  3) 请管理员确认 loginMustInputRandomCode=false。"
        )

    def _solve_captcha(self) -> Optional[str]:
        try:
            import io as _io

            import pytesseract
            from PIL import Image
        except ImportError:
            return None
        try:
            img_el = self.page.query_selector("#validImg")
            if not img_el:
                return None
            shot = img_el.screenshot()
            img = Image.open(_io.BytesIO(shot)).convert("L").point(lambda x: 0 if x < 128 else 255)
            text = pytesseract.image_to_string(
                img,
                config="--psm 8 -c tessedit_char_whitelist="
                "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
            ).strip()[:4]
            self._info(f"验证码识别：{text}")
            return text if len(text) >= 3 else None
        except Exception as exc:
            self._info(f"验证码识别异常：{exc}")
            return None

    # ── 登录态提取与续期 ────────────────────────────────────────────────
    def _page_user_info(self) -> Optional[Dict[str, Any]]:
        try:
            return self.page.evaluate(
                """async (path) => {
                    try {
                        const r = await fetch(path, {method: 'POST',
                            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                            credentials: 'include', body: ''});
                        const j = await r.json();
                        return j && String(j.code) === '200' ? j.data : null;
                    } catch (e) { return null; }
                }""",
                self.endpoints["user_info"],
            ) or None
        except Exception:
            return None

    def _capture_session(self, user: Dict[str, Any]) -> None:
        token = str(user.get("token") or "")
        if not token.startswith("Bearer-"):
            raise KdopAuthError("登录成功但未取到平台 token，接口无法调用")
        cookies = [
            {"name": c["name"], "value": c["value"], "domain": c.get("domain", ""), "path": c.get("path", "/")}
            for c in self.context.cookies()
        ] if self.context else []
        self.token, self.cookies, self.user = token, cookies, user
        self.expires_at = _jwt_exp(token) or int(time.time()) + 3600
        self.session_source = "fresh"
        self._persist_session()
        self._info(f"登录态已缓存，有效至 {datetime.fromtimestamp(self.expires_at):%Y-%m-%d %H:%M}")

    def _persist_session(self) -> None:
        if not self.token:
            return
        save_session(
            {
                "v": SESSION_VERSION,
                "base_url": self.base_url,
                "username": self.username,
                "token": self.token,
                "cookies": self.cookies,
                "user": {k: self.user.get(k) for k in ("userId", "userName", "email", "orgCode")},
                "expires_at": self.expires_at or int(time.time()) + 3600,
                "saved_at": int(time.time()),
            }
        )
        self._last_save = time.time()

    def _absorb_token(self, body: Any) -> None:
        """平台每次请求会下发滑动续期的新 token，及时落盘即可长期免登录。"""
        try:
            data = (body or {}).get("data") or {}
            token = data.get("token") if isinstance(data, dict) else None
        except Exception:
            return
        if not isinstance(token, str) or not token.startswith("Bearer-") or token == self.token:
            return
        self.token = token
        exp = _jwt_exp(token)
        if exp:
            self.expires_at = exp
        if time.time() - self._last_save > 60:
            self._persist_session()
            self._info("登录态已自动续期")

    # ── 传输层 ──────────────────────────────────────────────────────────
    def _cookie_header(self) -> str:
        return "; ".join(f"{c['name']}={c['value']}" for c in self.cookies if c.get("name"))

    def _http(self, path: str, params: Optional[Dict[str, Any]] = None, method: str = "POST") -> Dict[str, Any]:
        if not self.token:
            raise _SessionExpired("尚未登录")
        params = {k: ("" if v is None else str(v)) for k, v in (params or {}).items()}
        url = self.base_url + path
        data = None
        if method.upper() == "POST":
            data = urllib.parse.urlencode(params).encode("utf-8")
        elif params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)

        req = urllib.request.Request(url, data=data, method=method.upper())
        req.add_header("Authorization", self.token)
        req.add_header("Content-Type", "application/x-www-form-urlencoded;charset=UTF-8")
        req.add_header("Accept", "application/json, text/plain, */*")
        req.add_header("X-Requested-With", "XMLHttpRequest")
        req.add_header("User-Agent", UA)
        cookie = self._cookie_header()
        if cookie:
            req.add_header("Cookie", cookie)

        # 忽略系统/环境代理，避免内网访问被 http_proxy 劫持
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                text = resp.read().decode("utf-8", "replace")
                status = resp.status
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", "replace") if exc.fp else ""
            status = exc.code
        except urllib.error.URLError as exc:
            raise KdopError(f"网络异常：{exc.reason}") from exc

        body = None
        if text:
            try:
                body = json.loads(text)
            except Exception:
                body = None
        if body is None:
            # 网关鉴权失败会返回登录页 HTML，这里视为登录态失效
            raise _SessionExpired("接口返回非 JSON（登录态已失效）")
        if self._looks_like_auth_failure(body, status):
            raise _SessionExpired(str(body.get("message") or body.get("msg") or "登录态已失效"))
        self._absorb_token(body)
        return {"status": status, "json": body}

    @staticmethod
    def _looks_like_auth_failure(body: Any, status: int) -> bool:
        if status in (401, 403):
            return True
        if not isinstance(body, dict):
            return False
        message = str(body.get("message") or body.get("msg") or "")
        return any(hint in message for hint in AUTH_FAILURE_HINTS)

    def api(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        method: str = "POST",
        retry_on_expired: bool = True,
    ) -> Dict[str, Any]:
        """调用任意网关接口，返回 {"status", "json"}；登录态失效时自动重登重试。"""
        path = normalize_path(path)
        if not self.token:
            self.ensure_session()
        try:
            return self._http(path, params, method)
        except _SessionExpired:
            if not retry_on_expired:
                raise
            self._info("登录态已过期，自动重新登录后重试")
            self.browser_login()
            return self._http(path, params, method)

    def call(self, path: str, params: Optional[Dict[str, Any]] = None, method: str = "POST") -> Any:
        """调用并要求 code==200，返回 data。"""
        result = self.api(path, params, method)
        body = result.get("json") or {}
        if str(body.get("code")) != "200":
            raise KdopError(
                f"{path} 调用失败：{body.get('message') or body.get('msg') or result.get('status')}"
            )
        return body.get("data")

    # ── 业务层：身份 ────────────────────────────────────────────────────
    def whoami(self) -> Dict[str, Any]:
        user = self.ensure_session()
        self.call(self.endpoints["user_info"], {})
        return {
            "base_url": self.base_url,
            "login_user_id": user.get("userId") or self.username,
            "user_name": user.get("userName"),
            "email": user.get("email"),
            "org_code": user.get("orgCode"),
            "session_source": self.session_source,
            "expires_at": datetime.fromtimestamp(self.expires_at).strftime("%Y-%m-%d %H:%M") if self.expires_at else None,
        }

    # ── 业务层：版本与项目 ──────────────────────────────────────────────
    def list_versions(self, project_id: Optional[str] = None, all_projects: bool = False) -> List[Dict[str, Any]]:
        """版本列表。

        坑：接口只认 objectId（传 projectId 会 500）；且返回全平台版本，
        需按 parentId == 项目ID 过滤，否则会混入其它项目。
        """
        pid = project_id or self.project_id
        data: Any = None
        last_err = ""
        for key in ("objectId", "projectId"):
            try:
                data = self.call(self.endpoints["version_list"], {key: pid or ""})
                if isinstance(data, list):
                    break
            except KdopError as exc:
                last_err = str(exc)
                data = None
        if not isinstance(data, list):
            raise KdopError(
                f"版本列表接口不可用：{last_err}\n"
                "若未配置项目ID，请先 config set --project-id <项目ID>（可用 projects 命令查）"
            )
        if all_projects:
            return data
        # 匹配到就只留本项目；一条都不匹配说明 parentId 口径不同，原样返回并提示
        mine = [row for row in data if str(row.get("parentId") or "") == str(pid)]
        if not mine and data:
            self._info(f"未匹配到 parentId=={pid} 的版本，已返回全量 {len(data)} 条，请用 --all-projects 复核")
        return mine or data

    def list_projects(self, from_versions: bool = False) -> List[Dict[str, Any]]:
        """项目清单。

        首选平台「有权限的产品/项目目录」接口（顶栏项目切换器同源数据）；
        取不到时退回用全平台版本列表反推 parentId/parentName。
        """
        if not from_versions:
            try:
                data = self.call(self.endpoints["project_list"], {})
                rows = flatten_projects(data)
                if rows:
                    return rows
            except KdopError as exc:
                self._info(f"项目目录接口不可用（{exc}），改用版本列表反推")
        rows = self.list_versions(all_projects=True)
        seen: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            pid = str(row.get("parentId") or "")
            if not pid:
                continue
            name = row.get("parentName") or row.get("projectName") or ""
            item = seen.setdefault(pid, {"project_id": pid, "project_name": name, "version_count": 0})
            item["version_count"] += 1
            if not item["project_name"] and name:
                item["project_name"] = name
        return sorted(seen.values(), key=lambda i: (-i["version_count"], i["project_id"]))

    def version_index(self, project_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """版本名 → 版本行（含 objectId）。"""
        return {
            str(row.get("objectName")): row
            for row in self.list_versions(project_id=project_id)
            if row.get("objectName")
        }

    # ── 业务层：需求 / 缺陷 ─────────────────────────────────────────────
    def search_issues(
        self,
        app_id: int = 1,
        fields: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        page_size: int = 500,
        max_pages: int = 200,
    ) -> List[Dict[str, Any]]:
        """分页拉取 searchIssue 全量数据。app_id: 1=需求/工作项，2=缺陷。"""
        if fields is None:
            fields = STORY_FIELDS if app_id == 1 else DEFECT_FIELDS
        base: Dict[str, Any] = {
            "field": fields,
            "appId": str(app_id),
            "extraQueryField": "",
            "extraQueryFilterOptions": "[]",
        }
        base.update({k: v for k, v in (params or {}).items() if v is not None})
        if self.project_id:
            base.setdefault("projectId", self.project_id)

        collected: List[Dict[str, Any]] = []
        seen: set = set()
        for page in range(1, max_pages + 1):
            query = dict(base)
            query["page"] = str(page)
            query["size"] = str(page_size)
            data = self.call(self.endpoints["issue_search"], query)
            rows = (data or {}).get("list") or []
            added = 0
            for row in rows:
                key = row.get("id") or row.get("issueNum")
                if key in seen:
                    continue
                seen.add(key)
                collected.append(row)
                added += 1
            total = (data or {}).get("total") or 0
            self._info(f"appId={app_id} 第 {page} 页 +{added}，累计 {len(collected)}/{total}")
            if not rows or len(rows) < page_size or (total and page * page_size >= total):
                break
        return collected

    def fetch_issues_by_versions(
        self,
        version_names: Sequence[str],
        app_id: int = 1,
        project_id: Optional[str] = None,
        only_story: bool = False,
    ) -> List[Dict[str, Any]]:
        """按版本名精确拉取。

        坑：必须用 versionId(UUID) 过滤；versionIdName 只做单值匹配，
        跨多版本的需求会漏。版本名在版本目录里找不到时才退回 versionIdName。
        """
        index = self.version_index(project_id)
        merged: Dict[str, Dict[str, Any]] = {}
        unresolved: List[str] = []
        for name in version_names:
            row = index.get(name)
            if not row:
                unresolved.append(name)
                continue
            rows = self.search_issues(
                app_id=app_id,
                params={"projectId": project_id or self.project_id, "versionId": row.get("objectId")},
            )
            for item in rows:
                if only_story and "故事" not in str(item.get("issueTypeName") or ""):
                    continue
                key = str(item.get("id") or item.get("issueNum"))
                existed = merged.get(key)
                if existed:
                    if name not in existed["workbenchVersionNames"]:
                        existed["workbenchVersionNames"].append(name)
                else:
                    record = dict(item)
                    record["workbenchVersionNames"] = [name]
                    merged[key] = record

        if unresolved:
            self._info(f"版本目录中未找到：{unresolved}，改用 versionIdName 兜底匹配")
            for name in unresolved:
                rows = self.search_issues(
                    app_id=app_id,
                    params={"projectId": project_id or self.project_id, "versionIdName": name},
                )
                for item in rows:
                    if only_story and "故事" not in str(item.get("issueTypeName") or ""):
                        continue
                    names = {n.strip() for n in str(item.get("versionIdName") or "").split(",") if n.strip()}
                    if name not in names:
                        continue
                    key = str(item.get("id") or item.get("issueNum"))
                    record = merged.get(key) or dict(item)
                    record.setdefault("workbenchVersionNames", [])
                    if name not in record["workbenchVersionNames"]:
                        record["workbenchVersionNames"].append(name)
                    merged[key] = record
        return list(merged.values())

    def issues(
        self,
        version_names: Sequence[str],
        app_id: int = 1,
        project_id: Optional[str] = None,
        only_story: bool = False,
    ) -> List[Dict[str, Any]]:
        """版本下的需求或缺陷（app_id 1=需求 2=缺陷），已归一化。"""
        rows = self.fetch_issues_by_versions(
            version_names, app_id=app_id, project_id=project_id, only_story=only_story
        )
        normalizer = normalize_story if app_id == 1 else normalize_defect
        return [normalizer(row) for row in rows]

    def requirements(self, version_names: Sequence[str], project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """版本下的需求（只保留 issueTypeName 含「故事」的记录）。"""
        return self.issues(version_names, app_id=APP_IDS["story"], project_id=project_id, only_story=True)

    def issue_detail(self, issue_id: str, app_id: int = 1) -> Dict[str, Any]:
        """需求详情：优先详情接口，取不到就退回单条检索。"""
        try:
            data = self.call(self.endpoints["issue_detail"], {"id": issue_id, "appId": str(app_id)})
            if isinstance(data, dict) and data:
                return data
        except KdopError as exc:
            self._info(f"详情接口不可用（{exc}），退回单条检索")
        rows = self.search_issues(app_id=app_id, params={"id": issue_id}, page_size=1, max_pages=1)
        return rows[0] if rows else {}

    # ── 业务层：提交（KDOP 全局代码检索） ───────────────────────────────
    def search_commits(self, keyword: str, project_id: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        """按关键字在 KDOP「代码」域检索提交。

        端点与模块号来自平台前端 index/src/global-search.js：
        `service-core/global/search/listResult`，`module=4` 即代码提交。
        返回条目含 revision / message / repoType / projectId 等字段，按原始字段透传。
        """
        params: Dict[str, Any] = {"module": GLOBAL_SEARCH_MODULES["commit"], "keyword": keyword}
        if project_id or self.project_id:
            params["projectId"] = project_id or self.project_id
        try:
            data = self.call(self.endpoints["global_search"], params)
        except KdopError as exc:
            self._info(f"KDOP 提交检索失败（{exc}）")
            return []
        rows = data if isinstance(data, list) else (data or {}).get("list") or []
        normalized = [normalize_commit(row, keyword, "kdop") for row in rows[:limit]]
        return normalized

    # ── 追溯层：版本 → 需求 → 提交 ──────────────────────────────────────
    def trace_version(
        self,
        version_name: str,
        project_id: Optional[str] = None,
        include_kdop_commits: bool = True,
        include_git: bool = True,
        repos: Optional[Sequence[str]] = None,
        keyword_extra: Sequence[str] = (),
        since: Optional[str] = None,
        max_commits_per_requirement: int = 50,
    ) -> Dict[str, Any]:
        """给定版本名，产出「需求清单 + 每个需求的提交证据」。

        证据通道
        --------
        kdop : 平台「代码」域全局检索，按需求编号（FS-CBS-xxx）/ issueNum 命中提交信息。
        git  : 本地仓库 `git log --all --grep`，按同样的关键字命中提交信息。
        两者都是「提交信息含编号」的弱关联，报告中会标注 source，不做强断言。
        """
        pid = project_id or self.project_id
        versions = {str(r.get("objectName")): r for r in self.list_versions(project_id=pid)}
        version_row = versions.get(version_name)
        if not version_row:
            raise KdopError(
                f"版本 {version_name} 不存在于当前项目；可用 versions --match 检索相近版本名"
            )

        requirements = self.requirements([version_name], project_id=pid)
        self._info(f"版本 {version_name} 共 {len(requirements)} 条需求，开始匹配提交")

        # 1) 收集关键字 → 需求 的映射，供 git 侧一次性扫描（--grep 多值为 OR 语义）
        keyword_map: Dict[str, List[str]] = {}
        for req in requirements:
            for kw in requirement_keywords(req, keyword_extra):
                keyword_map.setdefault(kw, []).append(req["key"])
        self._info(f"关键字 {len(keyword_map)} 个")

        # 2) 本地 git 提交证据
        git_rows: List[Dict[str, Any]] = []
        if include_git:
            repo_paths = list(repos or self.repos or discover_repos())
            if repo_paths:
                self._info(f"扫描本地仓库 {len(repo_paths)} 个")
                git_rows = git_search_commits(repo_paths, list(keyword_map), since=since)
            else:
                self._info("未找到本地 git 仓库，跳过 git 通道（可 config set --repos 指定）")

        # 3) KDOP 提交证据（每个需求一次检索）+ 本地 git 证据回填
        attached: Dict[str, List[Dict[str, Any]]] = {req["key"]: [] for req in requirements}
        for req in requirements:
            bucket: List[Dict[str, Any]] = []
            if include_kdop_commits:
                for kw in req["keywords"]:
                    bucket.extend(self.search_commits(kw, project_id=pid, limit=max_commits_per_requirement))
            lowered = [kw.lower() for kw in req["keywords"]]
            for commit in git_rows:
                message = str(commit.get("message") or "").lower()
                matched = next((kw for kw in lowered if kw in message), None)
                if not matched:
                    continue
                record = dict(commit)
                record["keyword"] = record.get("keyword") or matched.upper()
                bucket.append(record)
            attached[req["key"]] = dedupe_commits(bucket)

        stats = summarize_trace(requirements, attached)
        return {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "base_url": self.base_url,
            "project_id": pid,
            "version": {
                "name": version_row.get("objectName"),
                "id": version_row.get("objectId"),
                "begin_date": ms_to_date(version_row.get("beginDate")),
                "plan_end_date": ms_to_date(version_row.get("planEndDate") or version_row.get("endDate")),
                "status": version_row.get("statusName") or version_row.get("status"),
            },
            "stats": stats,
            "requirements": [
                {**req, "commits": attached.get(req["key"], [])} for req in requirements
            ],
        }


# ══════════════════════════════════════════════════════════════════════════
# 归一化与统计（纯函数，便于单独复用/测试）
# ══════════════════════════════════════════════════════════════════════════
def flatten_projects(data: Any) -> List[Dict[str, Any]]:
    """把「产品 → 项目」目录树拍平成项目清单。

    平台返回结构在不同版本里可能是两级树，也可能直接是项目数组，
    这里统一抽出 objectId / objectName；父层名字记为 product_name。
    有子节点的节点按目录层处理，继续下钻。
    """
    rows: List[Dict[str, Any]] = []

    def walk(nodes: Any, parent_name: str = "") -> None:
        for node in nodes or []:
            if not isinstance(node, dict):
                continue
            pid = node.get("objectId") or node.get("projectId") or node.get("id")
            name = node.get("objectName") or node.get("projectName") or node.get("name") or ""
            children = node.get("children") or node.get("projects") or node.get("childList") or []
            if children:
                # 有子节点视为产品/目录层，继续下钻
                walk(children, name or parent_name)
                continue
            if pid:
                rows.append(
                    {"project_id": str(pid), "project_name": name, "product_name": parent_name}
                )

    if isinstance(data, list):
        walk(data)
    elif isinstance(data, dict):
        walk(data.get("list") or data.get("data") or [data])
    return rows


def normalize_story(row: Dict[str, Any]) -> Dict[str, Any]:
    """需求行归一化：key / 编号 / 标题 / 状态 / 经办人 / 计划日期 / 关键字。"""
    return {
        "key": str(row.get("id") or row.get("issueNum") or ""),
        "id": row.get("id"),
        "issue_num": row.get("issueNum"),
        "issue_type": row.get("issueTypeName"),
        "title": row.get("title"),
        "status": row.get("statusName") or row.get("status"),
        "assignee": row.get("assigneeName"),
        "module": row.get("moduleName") or row.get("productModuleName"),
        "version_names": [n.strip() for n in str(row.get("versionIdName") or "").split(",") if n.strip()],
        "workbench_version_names": row.get("workbenchVersionNames") or [],
        "plan_dev_done": ms_to_date(row.get("custom_589")),
        "plan_test_done": ms_to_date(row.get("custom_469")),
        "close_date": ms_to_date(row.get("closeDate")),
        "keywords": requirement_keywords(row),
        "raw": row,
    }


def normalize_defect(row: Dict[str, Any]) -> Dict[str, Any]:
    """缺陷行归一化：字段命名与需求保持一致，便于共用报表/表格渲染。"""
    return {
        "key": str(row.get("id") or row.get("issueNum") or ""),
        "id": row.get("id"),
        "issue_num": row.get("issueNum"),
        "issue_type": row.get("issueTypeName"),
        "title": row.get("title"),
        "status": row.get("statusName") or row.get("status"),
        "assignee": row.get("assigneeName"),
        "module": row.get("moduleName") or row.get("productModuleName"),
        "version_names": [n.strip() for n in str(row.get("versionIdName") or "").split(",") if n.strip()],
        "workbench_version_names": row.get("workbenchVersionNames") or [],
        "plan_dev_done": ms_to_date(row.get("plannedFinishDate") or row.get("dueDate")),
        "plan_test_done": "",
        "close_date": ms_to_date(row.get("closeDate")),
        "keywords": requirement_keywords(row),
        "raw": row,
    }


def requirement_keywords(row: Dict[str, Any], extra: Sequence[str] = ()) -> List[str]:
    """一个需求的可检索关键字：需求编号 + 标题里出现的 FS-CBS 编号 + 外部补充。"""
    keywords: List[str] = []
    issue_num = str(row.get("issueNum") or "").strip()
    if issue_num:
        keywords.append(issue_num)
    for match in REQ_NO_RE.findall(str(row.get("title") or "")):
        keywords.append(match.upper())
    for item in extra:
        if item:
            keywords.append(str(item))
    # 去重保序
    return list(dict.fromkeys(keywords))


def normalize_commit(row: Dict[str, Any], keyword: str, source: str) -> Dict[str, Any]:
    """提交行归一化：不同接口字段名不一致，这里统一到 hash/message/repo/files。"""
    return {
        "source": source,
        "keyword": keyword,
        "hash": row.get("revision") or row.get("commitId") or row.get("hash") or row.get("id"),
        "message": row.get("message") or row.get("commitMessage") or row.get("title") or "",
        "author": row.get("author") or row.get("authorName") or row.get("committerName"),
        "date": row.get("commitTime") or row.get("commitDate") or row.get("date") or row.get("createDate"),
        "repo": row.get("repoName") or row.get("repositoryName") or row.get("repoPath"),
        "repo_type": row.get("repoType"),
        "branch": row.get("branchName"),
        "files": row.get("files") or [],
        "raw": row,
    }


def dedupe_commits(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按 hash（无 hash 时按 message）去重，保留首次出现的来源。"""
    seen: set = set()
    result: List[Dict[str, Any]] = []
    for row in rows:
        key = str(row.get("hash") or row.get("message") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def summarize_trace(
    requirements: Sequence[Dict[str, Any]], attached: Dict[str, List[Dict[str, Any]]]
) -> Dict[str, Any]:
    """追溯结果统计：需求总数、有提交证据数、按来源计数。"""
    total = len(requirements)
    with_commits = sum(1 for req in requirements if attached.get(req["key"]))
    by_source: Dict[str, int] = {}
    for rows in attached.values():
        for row in rows:
            by_source[row.get("source", "unknown")] = by_source.get(row.get("source", "unknown"), 0) + 1
    return {
        "requirement_count": total,
        "requirements_with_commits": with_commits,
        "requirements_without_commits": total - with_commits,
        "coverage_rate": round(with_commits * 100 / total, 1) if total else 0.0,
        "commit_evidence_by_source": by_source,
    }


def summarize_stories(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """需求完成率（口径：开发完成 4 态、测试完成 2 态，完成率取两者平均）。"""
    stories = [r for r in rows if "故事" in str(r.get("issueTypeName") or "")]
    total = len(stories)
    dev_done = sum(1 for s in stories if str(s.get("statusName") or s.get("status")) in STORY_DEV_DONE)
    test_done = sum(1 for s in stories if str(s.get("statusName") or s.get("status")) in STORY_TEST_DONE)
    return {
        "总故事数": total,
        "开发完成数": dev_done,
        "测试完成数": test_done,
        "开发完成率": round(dev_done * 100 / total, 1) if total else 0.0,
        "测试完成率": round(test_done * 100 / total, 1) if total else 0.0,
        "需求完成率": round((dev_done + test_done) * 100 / (total * 2), 1) if total else 0.0,
    }


def summarize_defects(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """缺陷修复率/关闭率（只对传入行计数，调用方需保证 appId=2）。"""
    bugs = list(rows)
    total = len(bugs)
    fixed = sum(1 for b in bugs if str(b.get("statusName") or b.get("status")) in DEFECT_FIXED)
    closed = sum(1 for b in bugs if str(b.get("statusName") or b.get("status")) in DEFECT_CLOSED)
    return {
        "缺陷总数": total,
        "修复数": fixed,
        "关闭数": closed,
        "修复率": round(fixed * 100 / total, 1) if total else 0.0,
        "关闭率": round(closed * 100 / total, 1) if total else 0.0,
        "未关闭": total - closed,
    }


def ms_to_date(value: Any) -> str:
    """毫秒/秒时间戳或日期字符串 → YYYY-MM-DD。"""
    if value is None or value == "":
        return ""
    try:
        ts = int(value)
        if ts > 10**12:
            ts //= 1000
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        return str(value)[:10]


# ══════════════════════════════════════════════════════════════════════════
# 本地 git 通道
# ══════════════════════════════════════════════════════════════════════════
def discover_repos(root: Optional[str] = None, max_depth: int = 2) -> List[str]:
    """在给定目录（默认当前工作目录及其上两级）下发现 git 仓库。"""
    roots: List[Path] = []
    if root:
        roots.append(Path(root))
    else:
        here = Path.cwd()
        roots.extend([here, here.parent])
    found: List[str] = []
    seen: set = set()
    for base in roots:
        if not base.exists():
            continue
        for depth in range(0, max_depth + 1):
            pattern = "/".join(["*"] * depth) or "."
            for candidate in base.glob(f"{pattern}/.git" if depth else ".git"):
                repo = candidate.parent.resolve()
                if str(repo) in seen:
                    continue
                seen.add(str(repo))
                found.append(str(repo))
    return sorted(found)


def git_search_commits(
    repos: Sequence[str],
    keywords: Sequence[str],
    since: Optional[str] = None,
    max_count: int = 2000,
) -> List[Dict[str, Any]]:
    """在多个仓库里按提交信息关键字检索提交。

    一次 git log 传入多个 --grep（OR 语义），避免按仓库×关键字重复扫描。
    输出包含 hash / message / author / date / repo / files，供报告直接引用。
    """
    if not keywords:
        return []
    results: List[Dict[str, Any]] = []
    for repo in repos:
        if not (Path(repo) / ".git").exists():
            continue
        cmd = [
            "git", "-C", repo, "log", "--all", "--regexp-ignore-case",
            f"--max-count={max_count}",
            "--date=iso-strict",
            "--pretty=format:%x01%H%x02%an%x02%aI%x02%s",
            "--name-only",
        ]
        if since:
            cmd.append(f"--since={since}")
        for kw in keywords:
            cmd.extend(["--grep", kw])
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        except FileNotFoundError:
            raise KdopError("未找到 git 命令，请确认已安装 Git 并加入 PATH")
        if proc.returncode != 0:
            continue
        repo_name = Path(repo).name
        for block in proc.stdout.split("\x01"):
            if not block.strip():
                continue
            header, _, files_part = block.partition("\n")
            parts = header.split("\x02")
            if len(parts) < 4:
                continue
            commit_hash, author, date, subject = parts[0], parts[1], parts[2], parts[3]
            files = [line.strip() for line in files_part.splitlines() if line.strip()]
            lowered = subject.lower()
            matched = next((kw for kw in keywords if kw.lower() in lowered), "")
            results.append(
                {
                    "source": "git",
                    "keyword": matched.upper(),
                    "hash": commit_hash,
                    "message": subject,
                    "author": author,
                    "date": date,
                    "repo": repo_name,
                    "repo_path": repo,
                    "files": files,
                }
            )
    return results


# ══════════════════════════════════════════════════════════════════════════
# 渲染
# ══════════════════════════════════════════════════════════════════════════
def render_requirements_markdown(rows: Sequence[Dict[str, Any]], version_names: Sequence[str]) -> str:
    lines = [f"# 需求清单：{', '.join(version_names)}", ""]
    lines.append(f"共 {len(rows)} 条需求。")
    lines.append("")
    lines.append("| 编号 | 标题 | 状态 | 经办人 | 模块 | 计划开发完成 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in rows:
        title = str(row["title"] or "").replace("|", "\\|")
        lines.append(
            f"| {row['issue_num'] or ''} | {title} | {row['status'] or ''} | "
            f"{row['assignee'] or ''} | {row['module'] or ''} | {row['plan_dev_done'] or ''} |"
        )
    return "\n".join(lines)


def render_trace_markdown(result: Dict[str, Any]) -> str:
    version = result["version"]
    stats = result["stats"]
    lines = [
        f"# 需求提交追溯：{version['name']}",
        "",
        f"- 版本ID：{version['id']}",
        f"- 周期：{version['begin_date']} ~ {version['plan_end_date']}",
        f"- 需求总数：{stats['requirement_count']}，有提交证据：{stats['requirements_with_commits']}"
        f"（覆盖率 {stats['coverage_rate']}%）",
        f"- 证据来源分布：{stats['commit_evidence_by_source'] or '无'}",
        "",
        "> 提交证据为「提交信息含需求编号/issueNum」的弱关联，需人工复核。",
        "",
        "## 一、需求清单",
        "",
        "| 编号 | 标题 | 状态 | 经办人 | 提交数 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for req in result["requirements"]:
        title = str(req["title"] or "").replace("|", "\\|")
        lines.append(
            f"| {req['issue_num'] or ''} | {title} | {req['status'] or ''} | "
            f"{req['assignee'] or ''} | {len(req['commits'])} |"
        )

    lines.extend(["", "## 二、需求 → 提交明细", ""])
    for req in result["requirements"]:
        lines.append(f"### {req['issue_num'] or req['key']} {req['title'] or ''}")
        lines.append("")
        lines.append(f"- 状态：{req['status'] or ''}；经办人：{req['assignee'] or ''}；模块：{req['module'] or ''}")
        lines.append(f"- 检索关键字：{', '.join(req['keywords']) or '无'}")
        if not req["commits"]:
            lines.append("- 未找到提交证据（可能未提交、编号未写入提交信息，或代码不在本地仓库）")
            lines.append("")
            continue
        lines.append("")
        lines.append("| 来源 | 仓库 | 提交 | 日期 | 说明 | 文件数 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for commit in req["commits"]:
            message = str(commit.get("message") or "").replace("|", "\\|")[:80]
            short_hash = str(commit.get("hash") or "")[:12]
            lines.append(
                f"| {commit.get('source') or ''} | {commit.get('repo') or ''} | `{short_hash}` | "
                f"{ms_to_date(commit.get('date'))} | {message} | {len(commit.get('files') or [])} |"
            )
        lines.append("")

    no_commit = [req for req in result["requirements"] if not req["commits"]]
    if no_commit:
        lines.extend(["## 三、无提交证据的需求", ""])
        for req in no_commit:
            lines.append(f"- {req['issue_num'] or req['key']} {req['title'] or ''}")
        lines.append("")
    return "\n".join(lines)


def render_table(rows: Sequence[Dict[str, Any]]) -> str:
    """轻量文本表格，给终端直读用。"""
    if not rows:
        return "（无数据）"

    def cell(row: Dict[str, Any], key: str) -> str:
        value = row.get(key)
        return "" if value is None else str(value)

    keys = list(rows[0].keys())
    widths = {k: max(len(str(k)), *(len(cell(r, k)) for r in rows)) for k in keys}
    head = "  ".join(str(k).ljust(widths[k]) for k in keys)
    sep = "  ".join("-" * widths[k] for k in keys)
    body = ["  ".join(cell(r, k).ljust(widths[k]) for k in keys) for r in rows]
    return "\n".join([head, sep, *body])


# ══════════════════════════════════════════════════════════════════════════
# 接口发现（可选能力：扫描平台前端 JS 里的 gateway 路径）
# ══════════════════════════════════════════════════════════════════════════
def discover_endpoints(base_url: str, keyword: str = "", max_files: int = 30) -> Dict[str, Any]:
    """扫描平台前端静态资源，列出包含关键字的网关接口路径。

    用于接口升级后重新发现端点（不需要登录态）。只抓同源脚本，深度 1 层。
    """
    pattern = re.compile(r"(?:gateway|service(?:[iI][dD])?-\w+)/[A-Za-z0-9_\-/]+")
    entry = f"{base_url.rstrip('/')}/index.html"
    seen_files: set = set()
    endpoints: Dict[str, set] = {}
    queue = [entry]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def fetch(url: str) -> str:
        try:
            with opener.open(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=15) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception:
            return ""

    while queue and len(seen_files) < max_files:
        url = queue.pop(0)
        if url in seen_files:
            continue
        seen_files.add(url)
        text = fetch(url)
        if not text:
            continue
        for match in pattern.findall(text):
            path = normalize_path(match)
            if keyword and keyword.lower() not in path.lower():
                continue
            endpoints.setdefault(path, set()).add(url.rsplit("/", 1)[-1])
        for src in re.findall(r'src=["\']([^"\']+\.js)["\']', text) + re.findall(
            r'import\s+[\w{}\s,*]+\s+from\s+["\']([^"\']+\.js)["\']', text
        ):
            if src.startswith("http"):
                continue
            queue.append(urllib.parse.urljoin(url, src))
    return {
        "scanned_files": len(seen_files),
        "keyword": keyword,
        "endpoints": {path: sorted(srcs) for path, srcs in sorted(endpoints.items())},
    }


# ══════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════
def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _client(args, need_auth: bool = True) -> KdopClient:
    cfg = load_config(required=need_auth)
    return KdopClient(
        config=cfg,
        project_id=getattr(args, "project_id", None),
        headless=not getattr(args, "headed", False),
        timeout=int(getattr(args, "timeout", 60) or 60),
        keep_browser=getattr(args, "headed", False),
    )


def _cmd_config(args) -> int:
    if args.action == "set":
        if not (args.username and args.password):
            print("必须同时提供 --username 和 --password", file=sys.stderr)
            return 2
        patch: Dict[str, Any] = {"username": args.username, "password": args.password}
        if args.base_url:
            patch["base_url"] = args.base_url.rstrip("/")
        if args.project_id:
            patch["project_id"] = args.project_id
        if args.repos:
            patch["repos"] = args.repos
        path = update_config(**patch)
        if SESSION_PATH.exists():
            SESSION_PATH.unlink()  # 换账号立即失效旧登录态
        cfg = load_config(required=False)
        print(f"已保存配置：{path}")
        print(f"  服务器：{cfg['base_url']}")
        print(f"  账号：{cfg['username']}")
        print(f"  默认项目：{cfg.get('project_id') or '未设置（用 --project-id 指定）'}")
        print(f"  本地仓库：{cfg.get('repos') or '未设置（运行时自动发现）'}")
        return 0
    if args.action == "show":
        cfg = load_config(required=False)
        masked = dict(cfg)
        if masked.get("password"):
            masked["password"] = "*" * 8
        masked["config_file"] = str(CONFIG_PATH)
        masked["session_file"] = str(SESSION_PATH)
        masked["session_valid"] = load_session(cfg) is not None if cfg.get("username") else False
        _print_json(masked)
        return 0
    for path in (CONFIG_PATH, SESSION_PATH):
        if path.exists():
            path.unlink()
    print("已清除账号配置与登录态缓存")
    return 0


def _cmd_login(args) -> int:
    with _client(args) as client:
        user = client.ensure_session(force=not args.reuse)
    _print_json(
        {
            "登录账号": user.get("userId") or client.username,
            "姓名": user.get("userName"),
            "邮箱": user.get("email"),
            "登录方式": "复用本地登录态" if client.session_source == "cache" else "无头浏览器新登录",
            "会话文件": str(SESSION_PATH),
        }
    )
    return 0


def _cmd_whoami(args) -> int:
    with _client(args) as client:
        _print_json(client.whoami())
    return 0


def _cmd_logout(args) -> int:
    if SESSION_PATH.exists():
        SESSION_PATH.unlink()
        print("已删除本地登录态，下次运行会重新无头登录")
    else:
        print("没有本地登录态缓存")
    return 0


def _cmd_projects(args) -> int:
    with _client(args) as client:
        rows = client.list_projects(from_versions=args.from_versions)
    if args.out:
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"共 {len(rows)} 个项目，已写入 {args.out}", file=sys.stderr)
    _print_json(rows) if (args.json or not args.out) else None
    return 0


def _cmd_versions(args) -> int:
    with _client(args) as client:
        rows = client.list_versions(all_projects=args.all_projects)
    items = [
        {
            "name": row.get("objectName"),
            "id": row.get("objectId"),
            "parentId": row.get("parentId"),
            "project": row.get("parentName") or row.get("projectName"),
            "beginDate": ms_to_date(row.get("beginDate")),
            "planEndDate": ms_to_date(row.get("planEndDate") or row.get("endDate")),
            "status": row.get("statusName") or row.get("status"),
        }
        for row in rows
    ]
    items = [i for i in items if i["name"]]
    if args.match:
        pattern = re.compile(args.match, re.I)
        items = [i for i in items if pattern.search(i["name"])]
    items.sort(key=lambda i: (i["planEndDate"] or "9999", i["name"]))

    if args.out:
        Path(args.out).write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"共 {len(items)} 个版本，已写入 {args.out}", file=sys.stderr)
    if args.json or args.out:
        _print_json(items)
    else:
        print(render_table(items))
    return 0


def _cmd_requirements(args) -> int:
    with _client(args) as client:
        rows = client.issues(
            args.version,
            app_id=args.app_id,
            project_id=args.project_id,
            only_story=(args.app_id == 1),
        )
    if args.status:
        wanted = set(args.status)
        rows = [r for r in rows if r["status"] in wanted]
    if args.assignee:
        rows = [r for r in rows if args.assignee in str(r["assignee"] or "")]
    if args.out:
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"共 {len(rows)} 条，已写入 {args.out}", file=sys.stderr)
    if args.format == "md":
        print(render_requirements_markdown(rows, args.version))
    elif args.summary:
        raw = [r["raw"] for r in rows]
        _print_json(summarize_stories(raw) if args.app_id == 1 else summarize_defects(raw))
    else:
        _print_json(rows if not args.out or args.json else {"count": len(rows)})
    return 0


def _cmd_issue(args) -> int:
    with _client(args) as client:
        detail = client.issue_detail(args.issue_id, app_id=args.app_id)
    _print_json(normalize_story(detail) if args.app_id == 1 and detail else detail)
    return 0


def _cmd_commits(args) -> int:
    if args.local:
        # 本地 git 通道不依赖 KDOP 登录态，也不要求已配置账号
        config_repos: List[str] = []
        if CONFIG_PATH.exists():
            config_repos = list(load_config(required=False).get("repos") or [])
        repos = args.repo or config_repos or discover_repos()
        rows = git_search_commits(repos, args.keyword, since=args.since)
    else:
        with _client(args) as client:
            rows = []
            for keyword in args.keyword:
                rows.extend(client.search_commits(keyword, project_id=args.project_id, limit=args.limit))
            if args.repo:
                wanted = {Path(r).name for r in args.repo}
                rows = [r for r in rows if r.get("repo") in wanted]
    if args.out:
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"共 {len(rows)} 条提交，已写入 {args.out}", file=sys.stderr)
    _print_json(rows if not args.out or args.json else {"count": len(rows)})
    return 0


def _cmd_trace(args) -> int:
    with _client(args) as client:
        result = client.trace_version(
            args.version,
            project_id=args.project_id,
            include_kdop_commits=not args.no_kdop_commits,
            include_git=not args.no_git,
            repos=args.repo,
            keyword_extra=args.keyword_extra or [],
            since=args.since,
        )
    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"追溯结果已写入 {args.out}", file=sys.stderr)
    if args.format == "md":
        print(render_trace_markdown(result))
    elif args.format == "json":
        _print_json(result)
    else:
        stats = result["stats"]
        preview = [
            {
                "编号": req["issue_num"] or "",
                "标题": (req["title"] or "")[:40],
                "状态": req["status"] or "",
                "经办人": req["assignee"] or "",
                "提交数": len(req["commits"]),
            }
            for req in result["requirements"][: args.preview]
        ]
        print(render_table(preview))
        print(
            f"\n共 {stats['requirement_count']} 条需求，有提交证据 {stats['requirements_with_commits']} 条"
            f"（覆盖率 {stats['coverage_rate']}%）；证据来源 {stats['commit_evidence_by_source'] or '无'}",
            file=sys.stderr,
        )
    return 0


def _cmd_api(args) -> int:
    params: Dict[str, str] = {}
    for pair in args.data or []:
        if "=" in pair:
            key, value = pair.split("=", 1)
            params[key] = value
    with _client(args) as client:
        result = client.api(args.path, params, args.method)
    _print_json(result.get("json"))
    return 0


def _cmd_discover(args) -> int:
    cfg = load_config(required=False)
    base = args.base_url or cfg["base_url"]
    _print_json(discover_endpoints(base, keyword=args.keyword, max_files=args.max_files))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kdop_core",
        description="KDOP 通用访问客户端：自动登录 + 项目/版本/需求/缺陷/提交 + 需求追溯",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--headed", action="store_true", help="登录时显示浏览器窗口（调试用）")
    parser.add_argument("--project-id", help="项目ID；默认取配置")
    parser.add_argument("--timeout", type=int, default=60, help="单次请求超时（秒）")
    sub = parser.add_subparsers(dest="command", required=True)

    cfg = sub.add_parser("config", help="管理账号与本地配置")
    cfg.add_argument("action", choices=["set", "show", "clear"])
    cfg.add_argument("--username")
    cfg.add_argument("--password")
    cfg.add_argument("--base-url")
    cfg.add_argument("--project-id")
    cfg.add_argument("--repos", nargs="*", help="本地 git 仓库路径，供追溯 git 通道使用")
    cfg.set_defaults(func=_cmd_config)

    login = sub.add_parser("login", help="登录并缓存登录态（默认强制新登录）")
    login.add_argument("--reuse", action="store_true", help="未过期时直接复用，不重新登录")
    login.set_defaults(func=_cmd_login)

    sub.add_parser("whoami", help="校验登录态并输出当前账号").set_defaults(func=_cmd_whoami)
    sub.add_parser("logout", help="删除本地登录态").set_defaults(func=_cmd_logout)

    projects = sub.add_parser("projects", help="列出有权限的项目")
    projects.add_argument("--from-versions", action="store_true", help="改用全平台版本列表反推项目")
    projects.add_argument("--json", action="store_true")
    projects.add_argument("--out")
    projects.set_defaults(func=_cmd_projects)

    versions = sub.add_parser("versions", help="列出项目版本")
    versions.add_argument("--match", help="按版本名正则过滤，如 '1\\.7\\.9'")
    versions.add_argument("--all-projects", action="store_true", help="不过滤 parentId，返回全平台版本")
    versions.add_argument("--json", action="store_true")
    versions.add_argument("--out")
    versions.set_defaults(func=_cmd_versions)

    req = sub.add_parser("requirements", help="拉取版本下的需求（故事）或缺陷清单")
    req.add_argument("--version", action="append", required=True, help="版本名，可重复")
    req.add_argument("--app-id", type=int, default=1, choices=[1, 2], help="1=需求/故事 2=缺陷")
    req.add_argument("--status", action="append", help="状态名过滤，可重复")
    req.add_argument("--assignee", help="经办人过滤（包含匹配）")
    req.add_argument("--format", choices=["json", "md"], default="json")
    req.add_argument("--summary", action="store_true", help="输出完成率汇总")
    req.add_argument("--json", action="store_true", help="配合 --out 时也打印到 stdout")
    req.add_argument("--out")
    req.set_defaults(func=_cmd_requirements)

    issue = sub.add_parser("issue", help="查看单个需求/缺陷详情")
    issue.add_argument("issue_id")
    issue.add_argument("--app-id", type=int, default=1, choices=[1, 2], help="1=需求 2=缺陷")
    issue.set_defaults(func=_cmd_issue)

    commits = sub.add_parser("commits", help="按关键字检索提交（KDOP 代码域或本地 git）")
    commits.add_argument("--keyword", action="append", required=True, help="关键字，可重复（需求编号/issueNum）")
    commits.add_argument("--local", action="store_true", help="改用本地 git 检索，不走 KDOP")
    commits.add_argument("--repo", action="append", help="限定仓库路径/名称，可重复")
    commits.add_argument("--since", help="git 通道的起始时间，如 2026-01-01")
    commits.add_argument("--limit", type=int, default=200, help="KDOP 通道每个关键字最多返回条数")
    commits.add_argument("--out")
    commits.add_argument("--json", action="store_true")
    commits.set_defaults(func=_cmd_commits)

    trace = sub.add_parser("trace", help="版本 → 需求清单 → 每个需求的提交证据")
    trace.add_argument("--version", required=True, help="版本名")
    trace.add_argument("--repo", action="append", help="本地仓库路径，可重复；默认自动发现或读配置")
    trace.add_argument("--keyword-extra", action="append", help="需求额外检索关键字，可重复")
    trace.add_argument("--since", help="git 通道起始时间")
    trace.add_argument("--no-kdop-commits", action="store_true", help="跳过 KDOP 提交检索（快）")
    trace.add_argument("--no-git", action="store_true", help="跳过本地 git 通道")
    trace.add_argument("--format", choices=["table", "md", "json"], default="table")
    trace.add_argument("--preview", type=int, default=20, help="table 模式展示的需求条数")
    trace.add_argument("--out", help="追溯结果 JSON 落盘路径")
    trace.set_defaults(func=_cmd_trace)

    api = sub.add_parser("api", help="调用任意网关接口（原样返回 JSON）")
    api.add_argument("path", help="接口路径，如 /gateway/issue/issue/issue/searchIssue")
    api.add_argument("--data", action="append", help="表单参数 k=v，可重复")
    api.add_argument("--method", default="POST", choices=["POST", "GET"])
    api.set_defaults(func=_cmd_api)

    disc = sub.add_parser("discover", help="扫描平台前端 JS 发现网关接口（无需登录）")
    disc.add_argument("--keyword", default="", help="只保留路径包含该关键字的接口")
    disc.add_argument("--base-url", help="平台地址；默认取配置")
    disc.add_argument("--max-files", type=int, default=30)
    disc.set_defaults(func=_cmd_discover)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KdopAuthError as exc:
        print(f"登录相关错误：{exc}", file=sys.stderr)
        return 3
    except KdopConfigError as exc:
        print(f"配置缺失：{exc}", file=sys.stderr)
        return 5
    except KdopError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 4
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
