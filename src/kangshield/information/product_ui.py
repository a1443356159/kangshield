"""Self-contained HTML/CSS/JS for the local KangShield product."""

from __future__ import annotations

import html
import json


def dashboard_html(csrf_token: str) -> str:
    token = json.dumps(csrf_token)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>康盾</title>
  <style>{STYLE}</style>
</head>
<body>
  <div class="app-shell">
    <header class="topbar">
      <a class="brand" href="#overview" aria-label="康盾首页">
        <span class="brand-mark" aria-hidden="true"></span>
        <span><strong>康盾</strong></span>
      </a>
      <div class="topbar-actions">
        <span class="live-badge"><i></i> 守护中</span>
        <button class="icon-button" id="refresh-button" type="button" aria-label="立即刷新">↻</button>
      </div>
    </header>

    <main>
      <section class="hero" id="overview">
        <div>
          <p class="eyebrow">今天，康盾一直陪着您</p>
          <h1>家里的每一份变化，<br><span>都值得被看见。</span></h1>
          <p class="hero-copy">从行动状态、日常规律到可疑对话，康盾把值得留意的变化整理清楚，帮助家人及时关心、从容确认。</p>
        </div>
        <aside class="hero-status" aria-label="产品状态">
          <div class="status-orb"><span>♥</span><small>专属守护</small></div>
          <div>
            <strong>只和过去的自己比较</strong>
            <p>不和别人排名，更关注个人生活规律正在发生的变化。</p>
          </div>
        </aside>
      </section>

      <section class="notice" role="note">
        <span class="notice-icon">i</span>
        <p><strong>温馨提示</strong> 风险提示用于家庭照护和及时核实，不能代替医生诊断或对事件的最终认定。</p>
        <span class="refresh-copy" id="refresh-copy">正在读取最新数据…</span>
      </section>

      <section aria-labelledby="risk-title">
        <div class="section-heading">
          <div><p class="eyebrow">今日守护</p><h2 id="risk-title">需要关注的三件事</h2></div>
          <p id="generated-at">—</p>
        </div>
        <div class="risk-grid" id="cards" aria-live="polite">
          <div class="skeleton card-skeleton"></div><div class="skeleton card-skeleton"></div><div class="skeleton card-skeleton"></div>
        </div>
      </section>

      <section class="content-grid">
        <article class="panel trend-panel" aria-labelledby="trend-title">
          <div class="panel-heading"><div><p class="eyebrow">最近 28 天</p><h2 id="trend-title">变化趋势</h2></div><span class="panel-hint">分别查看，不合成总分</span></div>
          <div id="trends" class="trend-chart"><div class="empty">正在载入趋势…</div></div>
        </article>
        <article class="panel quality-panel" aria-labelledby="profile-title">
          <div class="panel-heading"><div><p class="eyebrow">个人专属</p><h2 id="profile-title">我的日常基线</h2></div><span id="profile-badge" class="status-pill">准备中</span></div>
          <div id="profile" class="profile-content"></div>
        </article>
      </section>

      <section class="panel wellbeing-panel" aria-labelledby="wellbeing-title">
        <div class="wellbeing-intro">
          <p class="eyebrow">每月关心自己一次</p>
          <h2 id="wellbeing-title">本月幸福感自评</h2>
          <p>用大约 1 分钟回顾过去两个星期的感受。结果会与个人日常基线一起参与心理健康风险判断。</p>
          <span>WHO-5 · 不是诊断 · 仅在本机保存</span>
        </div>
        <div id="wellbeing" class="wellbeing-content"><div class="empty">正在读取本月自评…</div></div>
      </section>

      <section class="panel events-panel" aria-labelledby="events-title">
        <div class="panel-heading events-heading">
          <div><p class="eyebrow">需要您看一眼</p><h2 id="events-title">近期提醒</h2></div>
          <div class="filters" id="filters" aria-label="近期提醒筛选">
            <button class="filter active" data-domain="all" type="button">全部</button>
            <button class="filter" data-domain="fall" type="button">跌倒</button>
            <button class="filter" data-domain="mental_wellbeing" type="button">心理</button>
            <button class="filter" data-domain="fraud" type="button">诈骗</button>
          </div>
        </div>
        <div id="timeline" class="timeline"><div class="empty">正在载入近期提醒…</div></div>
      </section>

      <section class="principles" aria-label="产品边界">
        <div><span>01</span><strong>不知道，就明确说不知道</strong><p>记录不足或设备暂时不可用时显示“暂无判断”，不会凭空猜测。</p></div>
        <div><span>02</span><strong>每条提醒都由家人确认</strong><p>您可以确认或忽略提醒，并留下只有照护者能够看到的记录。</p></div>
        <div><span>03</span><strong>异常片段安全归档</strong><p>连续录像不落本机；只有风险候选前后的短片段按期限归档，供照护者主动回看。</p></div>
      </section>
    </main>

    <footer><span>康盾</span><p>风险记录与异常短片段保存在本机 · 连续原始录像由云端账户管理 · <a href="/docs">使用说明与服务条款</a></p></footer>
  </div>

  <dialog id="review-dialog" class="review-dialog">
    <form method="dialog" id="review-form">
      <button class="dialog-close" value="cancel" aria-label="关闭">×</button>
      <p class="eyebrow">照护者确认</p>
      <h2 id="review-title">确认这条提醒</h2>
      <p id="review-summary" class="dialog-summary"></p>
      <label for="review-note">照护记录 <span>选填，仅照护者可见</span></label>
      <textarea id="review-note" maxlength="2000" rows="4" placeholder="可以记录现场情况、联系结果或后续安排"></textarea>
      <div class="dialog-actions">
        <button class="secondary" value="cancel">取消</button>
        <button class="danger" id="reject-button" type="button">不是这件事</button>
        <button class="primary" id="confirm-button" type="button">确认提醒</button>
      </div>
    </form>
  </dialog>
  <dialog id="wellbeing-dialog" class="review-dialog wellbeing-dialog">
    <form method="dialog" id="wellbeing-form">
      <button class="dialog-close" value="cancel" aria-label="关闭">×</button>
      <p class="eyebrow">过去两个星期</p>
      <h2>幸福感自评</h2>
      <p class="dialog-summary">请为每一项选择最接近您近期感受的频率。没有标准答案，按真实感受填写即可。</p>
      <div id="wellbeing-questions" class="wellbeing-questions"></div>
      <p class="instrument-note">采用世界卫生组织 WHO-5（2024），CC BY-NC-SA 3.0 IGO。分数较低只表示建议进一步关心和评估，不代表疾病诊断。</p>
      <div class="dialog-actions">
        <button class="secondary" value="cancel">稍后填写</button>
        <button class="primary" id="save-wellbeing-button" type="button">保存并更新风险</button>
      </div>
    </form>
  </dialog>
  <dialog id="playback-dialog" class="review-dialog playback-dialog">
    <form method="dialog">
      <button class="dialog-close" value="cancel" aria-label="关闭">×</button>
      <p class="eyebrow">安全事件回看</p>
      <h2 id="playback-title">查看异常片段</h2>
      <p id="playback-status" class="dialog-summary">正在准备异常片段…</p>
      <video id="cloud-playback" controls playsinline preload="metadata"></video>
      <p class="playback-privacy">优先播放本机按期限保存的异常短片段；本机归档缺失时才临时读取摄像头云录像。</p>
      <a id="playback-fallback" class="playback-fallback" target="_blank" rel="noreferrer" hidden>在新窗口打开片段</a>
      <div class="dialog-actions"><button class="secondary" value="cancel">关闭回看</button></div>
    </form>
  </dialog>
  <div class="toast" id="toast" role="status" aria-live="polite"></div>
  <script>window.KS_CSRF={token};</script>
  <script>{DASHBOARD_SCRIPT}</script>
</body>
</html>"""


def documentation_html(product_version: str) -> str:
    version = html.escape(product_version)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>康盾 · 使用说明与服务条款</title>
  <style>{STYLE}{DOCUMENTATION_STYLE}</style>
</head>
<body>
  <div class="app-shell docs-shell">
    <header class="topbar">
      <a class="brand" href="/" aria-label="返回康盾首页">
        <span class="brand-mark" aria-hidden="true"></span>
        <span><strong>康盾</strong></span>
      </a>
      <a class="docs-back" href="/">← 返回守护首页</a>
    </header>

    <main class="docs-main">
      <section class="docs-hero">
        <p class="eyebrow">使用说明 · 服务条款 · 技术透明</p>
        <h1>安心使用，<br><span>从了解边界开始。</span></h1>
        <p>康盾是一项在家庭本机运行的照护辅助工具。本页说明它能做什么、不能做什么，以及数据如何被处理。</p>
        <div class="docs-meta"><span>当前版本 {version}</span><span>条款生效日期 2026-08-30</span><span>本地试点</span></div>
      </section>

      <section class="docs-summary" aria-label="核心原则">
        <article><span>01</span><strong>风险服务只在本机</strong><p>看板默认仅能从当前电脑访问，不主动把风险结果发送到外部。</p></article>
        <article><span>02</span><strong>三项风险分别判断</strong><p>跌倒、心理健康和诈骗独立展示，不合成一个笼统总分。</p></article>
        <article><span>03</span><strong>重要事情由人确认</strong><p>系统只提供照护线索，家人或照护者应结合现场情况核实。</p></article>
      </section>

      <div class="docs-layout">
        <nav class="docs-nav" aria-label="文档目录">
          <strong>文档目录</strong>
          <a href="#terms">服务条款</a>
          <a href="#privacy">隐私与数据</a>
          <a href="#risk">风险等级说明</a>
          <a href="#technology">技术路线</a>
          <a href="#security">安全设计</a>
          <a href="#limitations">局限与责任</a>
          <a href="#licensing">来源与许可</a>
        </nav>

        <article class="docs-content">
          <section class="doc-section" id="terms">
            <p class="section-number">01 / 服务条款</p>
            <h2>服务性质与使用约定</h2>
            <p>康盾用于整理家庭环境中的行动变化、日常规律、本人月度自评和可疑对话线索，帮助使用者与照护者更早注意到值得核实的情况。开始使用前，应由本人或具有合法权限的照护者理解并接受以下边界。</p>
            <ul>
              <li><strong>不是紧急服务。</strong>康盾不会自动呼叫急救、报警或联系家属。发生现实危险时，应立即联系当地紧急服务和可信赖的人。</li>
              <li><strong>不是医疗诊断。</strong>心理健康与跌倒等级不能代替医生检查、量表诊断、治疗建议或康复方案。</li>
              <li><strong>不是诈骗认定。</strong>诈骗域只表示摄像头实际听到的环境对话中出现可疑语境，不能证明某人实施诈骗。</li>
              <li><strong>依法取得同意。</strong>安装者应确保对家庭摄像、环境录音和照护记录拥有必要权限，并向可能进入采集范围的人提供适当告知。</li>
              <li><strong>由照护者复核。</strong>使用者应核实重要提醒、维护设备可用，并避免仅凭一个等级作出医疗、财务或人身安全决定。</li>
            </ul>
          </section>

          <section class="doc-section" id="privacy">
            <p class="section-number">02 / 隐私与数据</p>
            <h2>尽量少保存，也让分享有边界</h2>
            <div class="doc-grid">
              <div><strong>本机长程记录</strong><p>按个人分库存放日级特征、风险历史、候选事件、复核审计和 WHO-5 月度答案，默认不会上传到远程平台。</p></div>
              <div><strong>媒体最小化</strong><p>连续原始录像由摄像头云服务按用户配置保存，本机只把产生风险候选的事件前后短片段归档为带声音 MP4。语音命中事件最多保留 120 字规范化转写，供本机照护者理解原因。</p></div>
              <div><strong>两种导出</strong><p>家庭照护版可包含原因和复核记录；安心分享版移除身份、原始指标、问卷答案、对话文字、备注、路径和精确事件时间。</p></div>
              <div><strong>保留与删除</strong><p>异常片段默认保留 30 天，并受每人 2 GiB 上限约束；删除个人数据会一并删除本机片段。云端原始录像仍由云服务账户另行管理。</p></div>
            </div>
          </section>

          <section class="doc-section" id="risk">
            <p class="section-number">03 / 风险等级说明</p>
            <h2>等级是照护优先级，不是发生概率</h2>
            <div class="level-table" role="table" aria-label="风险等级含义">
              <div role="row"><strong role="cell">0</strong><span role="cell">暂未发现</span><p role="cell">在规定的数据覆盖内未发现有效证据。</p></div>
              <div role="row"><strong role="cell">1</strong><span role="cell">需要留意</span><p role="cell">出现一项轻度变化或单类可疑线索。</p></div>
              <div role="row"><strong role="cell">2</strong><span role="cell">建议确认</span><p role="cell">出现较明显变化、待确认事件或需进一步关心的自评结果。</p></div>
              <div role="row"><strong role="cell">3</strong><span role="cell">优先处理</span><p role="cell">出现人工确认、高强度组合证据或持续性明显变化。</p></div>
              <div role="row"><strong role="cell">—</strong><span role="cell">暂无判断</span><p role="cell">数据不足、过期或分析失败时明确不评分。</p></div>
            </div>
            <h3>三种风险如何形成</h3>
            <ul>
              <li><strong>跌倒：</strong>结合姿态事件、求助语音、人工确认和本人行动基线；24 小时内有效姿态不足时不能仅凭“没发现”给 0。</li>
              <li><strong>心理健康：</strong>比较本人过去 28 天的日间出现、活动、语言互动和已确认睡眠规律，并纳入每月 WHO-5 自评。问卷低于建议进一步评估的界线时至少为 2，正常问卷不会抵消其他风险证据。</li>
              <li><strong>诈骗：</strong>仅分析摄像头能听到的环境对话，匹配凭证索取、转账投资、身份冒充、紧迫保密和远程控制语境，并排除反诈宣传、新闻、转述和明确否定。</li>
            </ul>
          </section>

          <section class="doc-section" id="technology">
            <p class="section-number">04 / 技术路线</p>
            <h2>从家庭记录到可解释提醒</h2>
            <div class="route-flow" aria-label="技术处理流程">
              <div><span>1</span><strong>连续内存守护</strong><p>目标单机位按段取流；连续原始流不落盘，仅异常事件窗口生成本机归档。</p></div>
              <div><span>2</span><strong>关键窗口分析</strong><p>轻量运动与声音活动先筛选，姿态和普通话转写只处理选中内容。</p></div>
              <div><span>3</span><strong>个人建模</strong><p>日级特征建立 28 天个人基线，问卷补充本人主动感受。</p></div>
              <div><span>4</span><strong>规则评分</strong><p>三域使用版本化 0–3/null 规则，并保存证据摘要。</p></div>
              <div><span>5</span><strong>照护闭环</strong><p>本地看板、人工复核、趋势和双版本报告持续更新。</p></div>
            </div>
            <p class="callout"><strong>以个人为中心：</strong>康盾不与同龄人排名，也不输出人群概率。心理规律和行动变化主要与同一个人过去的有效记录比较。</p>
          </section>

          <section class="doc-section" id="security">
            <p class="section-number">05 / 安全设计</p>
            <h2>本地访问与最小接口</h2>
            <ul>
              <li>HTTP 服务只绑定 <code>127.0.0.1</code>，不默认开放局域网或公网访问。</li>
              <li>填写问卷、复核事件和删除记录要求同源请求及随机 CSRF 令牌；JSON 请求设有大小限制。</li>
              <li>页面启用内容安全、禁止嵌入和浏览器权限限制，不申请摄像头、麦克风或定位权限。</li>
              <li>当前完整分段和模型输入不落盘；候选事件前 10 秒至后 20 秒可保存为 owner-only MP4，并记录摘要、大小和到期时间。</li>
              <li>服务没有任意文件或完整逐字稿读取路由；本机片段只能通过同源复核后的短期随机播放令牌访问。</li>
              <li>首页使用聚合读取，一次刷新只构建一次风险快照；写操作串行化，减少并发复核造成的状态竞争。</li>
            </ul>
          </section>

          <section class="doc-section" id="limitations">
            <p class="section-number">06 / 局限与责任</p>
            <h2>系统可能漏报，也可能误报</h2>
            <p>遮挡、夜间画质、设备离线、远场噪声、多人交叉、电话另一端不可听、姿态模型失败或个人基线不足都可能影响结果。康盾采用“证据不足就不评分”的原则降低补猜，但这不能消除全部错误。</p>
            <p>当前规则标记为本地未验证试点，不应宣传为已完成临床验证、诈骗鉴定或已知准确率的预测产品。使用者仍应结合现场、本人感受、家属沟通和专业人员意见作出决定。</p>
          </section>

          <section class="doc-section" id="licensing">
            <p class="section-number">07 / 来源与许可</p>
            <h2>量表来源与条款更新</h2>
            <p>月度幸福感自评采用世界卫生组织 WHO-5 2024 开放版本，许可为 CC BY-NC-SA 3.0 IGO。查看 <a href="https://www.who.int/publications/m/item/WHO-UCN-MSD-MHE-2024.01" target="_blank" rel="noreferrer">WHO 官方发布页</a>。使用该量表不表示世界卫生组织认可康盾。</p>
            <p>产品功能、风险策略或数据范围发生实质变化时，应同步更新本页版本和生效日期。对本机数据删除、设备权限或运行异常有疑问时，请联系安装和维护这台设备的本地管理员。</p>
          </section>
        </article>
      </div>
    </main>

    <footer><span>康盾</span><p><a href="/">返回守护首页</a> · 本文档随本地产品一同提供</p></footer>
  </div>
</body>
</html>"""


def offline_report_html(payload: dict[str, object]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    visibility = str(payload.get("visibility", "owner_only"))
    label = "家庭照护版" if visibility == "owner_only" else "安心分享版"
    script = OFFLINE_SCRIPT if visibility == "owner_only" else OFFLINE_PUBLIC_SCRIPT
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>康盾 · 守护报告</title><style>{STYLE}</style></head>
<body><div class="app-shell report-shell"><header class="topbar"><div class="brand"><span class="brand-mark" aria-hidden="true"></span><span><strong>康盾</strong></span></div><span class="status-pill">{html.escape(label)}</span></header>
<main><section class="hero report-hero"><div><p class="eyebrow">守护报告</p><h1>每一份变化，<br><span>都有迹可循。</span></h1><p class="hero-copy">这份报告用于家庭照护和及时核实，不能代替医生诊断或对事件的最终认定。</p></div></section>
<section><div class="section-heading"><div><p class="eyebrow">当前状态</p><h2>需要关注的三件事</h2></div></div><div class="risk-grid" id="cards"></div></section>
<section class="content-grid"><article class="panel trend-panel"><div class="panel-heading"><div><p class="eyebrow">最近 28 天</p><h2>变化趋势</h2></div></div><div id="trends" class="trend-chart"></div></article><article class="panel quality-panel"><div class="panel-heading"><div><p class="eyebrow">关于这份报告</p><h2>阅读说明</h2></div></div><div id="quality" class="quality-grid"></div></article></section>
<section class="panel events-panel"><div class="panel-heading"><div><p class="eyebrow">近期记录</p><h2>需要留意的事情</h2></div></div><div id="timeline" class="timeline"></div></section></main>
<footer><span>康盾</span><p>风险提示仅供家庭照护参考</p></footer></div>
<script type="application/json" id="payload">{serialized}</script><script>{script}</script></body></html>"""


STYLE = r"""
:root{--ink:#122821;--muted:#62756e;--paper:#f5f3ec;--card:#fffefa;--line:#dfe5df;--green:#176b57;--green-2:#35a37f;--mint:#dff2e8;--amber:#d7902d;--amber-soft:#fff2dc;--red:#c6534b;--red-soft:#fbe7e4;--blue:#39779f;--shadow:0 18px 55px rgba(26,62,52,.08);font-family:Inter,"Noto Sans SC","Microsoft YaHei",system-ui,sans-serif;color:var(--ink);background:var(--paper);font-synthesis:none}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(circle at 85% -10%,#d8eee4 0,transparent 28rem),var(--paper)}button,textarea{font:inherit}.app-shell{min-height:100vh}.topbar{height:82px;max-width:1240px;margin:auto;padding:0 28px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(23,107,87,.12)}.brand{display:flex;align-items:center;gap:12px;color:var(--ink);text-decoration:none}.brand-mark{width:42px;height:42px;border-radius:14px;display:grid;place-items:center;color:#fff;background:var(--green);font:800 21px/1 Georgia,serif;box-shadow:0 7px 18px #176b5738}.brand strong,.brand small{display:block}.brand strong{font-size:18px;letter-spacing:.01em}.brand small{font-size:11px;color:var(--muted);margin-top:2px;letter-spacing:.08em}.topbar-actions{display:flex;align-items:center;gap:10px}.live-badge,.status-pill{display:inline-flex;align-items:center;gap:7px;border:1px solid #cbdcd4;border-radius:999px;padding:7px 12px;font-size:12px;color:var(--green);background:#f8fffb}.live-badge i{width:7px;height:7px;background:#27a878;border-radius:50%;box-shadow:0 0 0 5px #27a8781f;animation:pulse 1.8s infinite}.icon-button{width:36px;height:36px;border:1px solid #d5ded9;border-radius:50%;background:#fffefa;color:var(--green);cursor:pointer;font-size:20px;transition:.2s}.icon-button:hover{transform:rotate(45deg);border-color:var(--green)}main{max-width:1184px;margin:auto;padding:54px 28px 72px}.hero{display:grid;grid-template-columns:1.45fr .75fr;gap:38px;align-items:end;padding:24px 0 52px}.eyebrow{margin:0 0 10px;color:var(--green);font-size:11px;font-weight:800;letter-spacing:.18em}.hero h1{font:600 clamp(44px,7vw,78px)/1.02 Georgia,"Songti SC",serif;letter-spacing:-.04em;margin:0;max-width:800px}.hero h1 span{color:var(--green)}.hero-copy{max-width:620px;margin:25px 0 0;color:var(--muted);font-size:17px;line-height:1.85}.hero-status{display:flex;align-items:center;gap:18px;background:linear-gradient(140deg,#113d32,#176b57);color:white;border-radius:28px;padding:23px;box-shadow:0 22px 44px #176b572b}.status-orb{flex:0 0 auto;width:78px;height:78px;border:1px solid #ffffff40;border-radius:50%;display:grid;place-content:center;text-align:center;background:#ffffff0d}.status-orb span{font:600 30px/1 Georgia,serif}.status-orb small{font-size:9px;opacity:.75}.hero-status strong{font-size:15px}.hero-status p{font-size:12px;line-height:1.55;opacity:.72;margin:6px 0 0}.notice{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:13px;padding:14px 17px;background:#fffaf0;border:1px solid #eedcb9;border-radius:16px;margin-bottom:56px;color:#6c542f;font-size:13px}.notice p{margin:0}.notice-icon{width:24px;height:24px;border-radius:50%;display:grid;place-items:center;background:var(--amber);color:#fff;font:700 13px Georgia}.notice code{font-size:11px}.refresh-copy{color:#92754a;font-size:11px}.section-heading,.panel-heading{display:flex;align-items:end;justify-content:space-between;gap:20px;margin-bottom:20px}.section-heading h2,.panel-heading h2{margin:0;font:600 29px/1.2 Georgia,"Songti SC",serif}.section-heading>p,.panel-hint{font-size:12px;color:var(--muted);margin:0}.risk-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}.risk-card{position:relative;overflow:hidden;min-height:338px;padding:24px;border:1px solid #e2e7e2;border-radius:25px;background:var(--card);box-shadow:var(--shadow);display:flex;flex-direction:column}.risk-card::after{content:"";position:absolute;width:170px;height:170px;border-radius:50%;right:-85px;top:-90px;background:var(--accent-soft)}.risk-card-head{display:flex;justify-content:space-between;gap:12px;position:relative;z-index:1}.domain-icon{width:45px;height:45px;border-radius:15px;display:grid;place-items:center;background:var(--accent-soft);color:var(--accent);font-size:20px}.risk-state{text-align:right}.risk-state strong{display:block;font-size:12px;color:var(--accent)}.risk-state span{font-size:10px;color:var(--muted)}.score-row{display:flex;align-items:center;gap:17px;margin:27px 0 20px}.score-ring{width:96px;height:96px;flex:0 0 auto;border-radius:50%;display:grid;place-items:center;background:conic-gradient(var(--accent) calc(var(--score)*25%),#edf0ed 0);position:relative}.score-ring::before{content:"";position:absolute;inset:8px;border-radius:50%;background:var(--card)}.score-ring strong{position:relative;font:600 35px/1 Georgia,serif}.score-ring small{position:relative;color:var(--muted);font-size:10px}.score-copy strong{font-size:18px}.score-copy p{font-size:12px;color:var(--muted);line-height:1.55;margin:5px 0}.reason{font-size:13px;line-height:1.65;margin:0 0 18px;min-height:42px}.coverage{margin-top:auto}.coverage-line{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-bottom:7px}.coverage-bar{height:6px;border-radius:6px;background:#ebeeeb;overflow:hidden}.coverage-bar i{display:block;height:100%;width:var(--coverage);background:var(--accent);border-radius:inherit}.risk-fall{--accent:#d16a45;--accent-soft:#f9e8df}.risk-mental_wellbeing{--accent:#397f78;--accent-soft:#e1f0ec}.risk-fraud{--accent:#765b9f;--accent-soft:#eee8f7}.risk-null{--accent:#7a8983;--accent-soft:#edf0ee}.content-grid{display:grid;grid-template-columns:1.35fr .75fr;gap:18px;margin-top:50px}.panel{background:var(--card);border:1px solid #e2e7e2;border-radius:25px;padding:24px;box-shadow:var(--shadow)}.trend-chart{min-height:254px}.trend-row{display:grid;grid-template-columns:92px 1fr;align-items:center;gap:15px;margin:19px 0}.trend-label strong{font-size:13px;display:block}.trend-label small{font-size:10px;color:var(--muted)}.trend-bars{height:54px;display:flex;align-items:end;gap:5px;border-bottom:1px solid #dfe5df;padding:0 2px}.trend-bar{flex:1;min-width:5px;max-width:20px;height:calc((var(--score) + .3)*23%);border-radius:5px 5px 1px 1px;background:var(--accent);opacity:.85;position:relative;transition:.2s}.trend-bar:hover{opacity:1;transform:translateY(-2px)}.trend-bar[data-null="true"]{height:4px;background:#ccd5d1}.trend-dates{display:flex;justify-content:space-between;margin:8px 0 0 107px;color:var(--muted);font-size:9px}.quality-grid{display:grid;gap:10px}.quality-item{padding:14px;border-radius:16px;background:#f6f8f5;border:1px solid #e7ebe7}.quality-item span{display:block;color:var(--muted);font-size:10px;margin-bottom:5px}.quality-item strong{font-size:14px}.quality-item small{display:block;color:var(--muted);font-size:10px;margin-top:4px}.status-pill.stale{color:#9b5f24;background:#fff6e8;border-color:#ecd2a8}.status-pill.good{color:var(--green);background:#edfaf4}.events-panel{margin-top:18px}.events-heading{align-items:center}.filters{display:flex;gap:6px;padding:4px;background:#f0f3ef;border-radius:12px}.filter{border:0;border-radius:9px;background:transparent;color:var(--muted);padding:7px 11px;font-size:11px;cursor:pointer}.filter.active{color:var(--green);background:#fff;box-shadow:0 2px 8px #153c3020}.timeline{display:grid;gap:10px}.event{display:grid;grid-template-columns:auto 1fr auto;gap:15px;align-items:start;padding:17px;border:1px solid #e5e9e5;border-radius:18px;background:#fff}.event-dot{width:38px;height:38px;border-radius:13px;display:grid;place-items:center;background:var(--accent-soft);color:var(--accent)}.event-title{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.event-title strong{font-size:14px}.event-title .status-pill{padding:3px 8px;font-size:9px}.event-copy{margin:7px 0 0;color:var(--muted);font-size:12px;line-height:1.55}.event-audit{margin:7px 0 0;font-size:10px;color:#83908b}.review-button{border:1px solid #cbdad3;border-radius:10px;background:#f7fffb;color:var(--green);padding:8px 11px;font-size:11px;cursor:pointer}.review-button:hover{background:var(--green);color:#fff}.principles{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;margin-top:48px;border:1px solid #dde4df;border-radius:24px;overflow:hidden;background:#dde4df}.principles>div{padding:25px;background:#edf3ef}.principles span{display:block;font:600 24px Georgia;color:#a8b9b1}.principles strong{display:block;margin:12px 0 6px;font-size:14px}.principles p{margin:0;color:var(--muted);font-size:11px;line-height:1.65}footer{max-width:1184px;margin:auto;padding:26px 28px 42px;border-top:1px solid #dce4df;display:flex;justify-content:space-between;color:var(--muted);font-size:11px}footer span{font-weight:800;color:var(--ink)}footer p{margin:0}.empty{min-height:120px;display:grid;place-items:center;text-align:center;color:var(--muted);font-size:12px;border:1px dashed #d4ddd8;border-radius:16px;padding:20px}.skeleton{background:linear-gradient(90deg,#edf0ed 25%,#f8faf7 50%,#edf0ed 75%);background-size:200% 100%;animation:shimmer 1.4s infinite}.card-skeleton{height:338px;border-radius:25px}.review-dialog{width:min(520px,calc(100% - 30px));border:0;border-radius:24px;padding:0;box-shadow:0 30px 90px #102b2260}.review-dialog::backdrop{background:#102b2268;backdrop-filter:blur(4px)}.review-dialog form{position:relative;padding:28px}.dialog-close{position:absolute;right:18px;top:16px;width:34px;height:34px;border:0;border-radius:50%;background:#f0f3ef;font-size:20px;color:var(--muted);cursor:pointer}.review-dialog h2{font:600 27px Georgia;margin:0}.dialog-summary{color:var(--muted);font-size:13px;line-height:1.65;margin:15px 0 20px}.review-dialog label{display:block;font-size:12px;font-weight:700}.review-dialog label span{display:block;color:var(--muted);font-size:10px;font-weight:400;margin-top:3px}.review-dialog textarea{width:100%;margin-top:9px;border:1px solid #d6ded9;border-radius:13px;padding:12px;resize:vertical;outline:none}.review-dialog textarea:focus{border-color:var(--green);box-shadow:0 0 0 3px #176b5715}.dialog-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:20px}.dialog-actions button{border-radius:11px;padding:9px 13px;cursor:pointer}.secondary{border:1px solid #d7dfda;background:#fff;color:var(--muted)}.primary{border:1px solid var(--green);background:var(--green);color:#fff}.danger{border:1px solid #ebc5c1;background:#fff7f6;color:var(--red)}.toast{position:fixed;right:22px;bottom:22px;max-width:340px;background:#173f34;color:#fff;padding:12px 16px;border-radius:12px;font-size:12px;box-shadow:0 16px 45px #102b2240;opacity:0;transform:translateY(12px);pointer-events:none;transition:.2s}.toast.show{opacity:1;transform:none}.report-shell .topbar{max-width:1120px}.report-shell main{max-width:1064px}.report-hero{grid-template-columns:1fr;padding-bottom:42px}.report-hero h1{font-size:58px}.report-shell .events-panel{margin-top:18px}
@keyframes pulse{50%{box-shadow:0 0 0 8px #27a87808}}@keyframes shimmer{to{background-position:-200% 0}}
@media(max-width:900px){.hero,.content-grid{grid-template-columns:1fr}.hero-status{max-width:500px}.risk-grid{grid-template-columns:1fr}.risk-card{min-height:300px}.principles{grid-template-columns:1fr}.notice{grid-template-columns:auto 1fr}.refresh-copy{grid-column:2}.events-heading{align-items:flex-start;flex-direction:column}.filters{width:100%;overflow:auto}.event{grid-template-columns:auto 1fr}.event .review-button{grid-column:2;justify-self:start}}
@media(max-width:560px){.topbar{height:70px;padding:0 18px}.live-badge{display:none}main{padding:32px 16px 54px}.hero{padding:10px 0 35px}.hero h1{font-size:43px}.hero-copy{font-size:14px}.hero-status{border-radius:20px;padding:17px}.notice{margin-bottom:42px}.section-heading{align-items:flex-start;flex-direction:column}.panel{padding:18px;border-radius:20px}.trend-row{grid-template-columns:75px 1fr;gap:8px}.trend-dates{margin-left:83px}.principles{border-radius:20px}footer{padding:22px 18px;display:block}footer p{margin-top:6px}.dialog-actions{display:grid;grid-template-columns:1fr 1fr}.dialog-actions .secondary{grid-column:1/-1;order:3}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;animation:none!important;transition:none!important}}
.score-ring{background:conic-gradient(var(--accent) var(--score-pct,0%),#edf0ed 0)}.trend-bar{height:var(--bar-height,4px)}
.brand-mark{position:relative;background:transparent;box-shadow:none;overflow:visible}.brand-mark::before{content:"";position:absolute;inset:2px 5px 3px;background:linear-gradient(145deg,#1b7a62,#0f4f40);clip-path:polygon(50% 0,94% 17%,86% 72%,50% 100%,14% 72%,6% 17%);box-shadow:0 8px 18px #176b5730}.brand-mark::after{content:"";position:absolute;width:11px;height:19px;left:17px;top:11px;background:#d9f3e7;border-radius:100% 0 100% 0;transform:rotate(-12deg)}
.profile-content{display:grid;gap:14px}.profile-summary{padding:15px;border-radius:17px;background:linear-gradient(135deg,#edf8f2,#f9fcfa);border:1px solid #dcebe3}.profile-summary strong{display:block;font-size:14px}.profile-summary p{margin:6px 0 0;color:var(--muted);font-size:11px;line-height:1.6}.profile-features{display:grid;grid-template-columns:1fr 1fr;gap:9px}.profile-feature{padding:12px;border-radius:14px;background:#f7f8f5;border:1px solid #e6ebe7}.profile-feature span{display:block;color:var(--muted);font-size:10px}.profile-feature strong{display:block;margin-top:5px;font-size:12px}.profile-feature.changed{background:#fff6e8;border-color:#efd9b6}.profile-feature.changed strong{color:#9b5f24}.profile-feature.unavailable{opacity:.62}.voice-quote{position:relative;margin:10px 0 2px;padding:13px 14px 13px 34px;border-radius:14px;background:#f4effa;color:#5c477a;font-size:12px;line-height:1.65}.voice-quote::before{content:"“";position:absolute;left:12px;top:5px;font:700 26px Georgia;color:#866dae}.event-basis{display:inline-block;margin-top:8px;color:var(--green);font-size:10px}.risk-basis{display:inline-flex;align-items:center;gap:5px;color:var(--muted);font-size:10px;margin-top:-10px;margin-bottom:15px}.risk-basis::before{content:"";width:5px;height:5px;border-radius:50%;background:var(--accent)}
.wellbeing-panel{margin:18px 0 0;display:grid;grid-template-columns:minmax(250px,.72fr) 1.28fr;gap:28px;background:linear-gradient(135deg,#143f35,#1c6d58);color:#fff;border:0}.wellbeing-intro{align-self:center}.wellbeing-intro .eyebrow{color:#a8e1ca}.wellbeing-intro h2{margin:0;font:600 32px/1.2 Georgia,"Songti SC",serif}.wellbeing-intro>p:not(.eyebrow){max-width:390px;margin:13px 0;color:#d9ebe4;font-size:13px;line-height:1.75}.wellbeing-intro>span{font-size:10px;color:#acd0c2}.wellbeing-content{min-height:175px;padding:19px;border-radius:20px;background:#fffefa;color:var(--ink)}.wellbeing-content .empty{min-height:135px}.checkin-head{display:flex;align-items:flex-start;justify-content:space-between;gap:15px}.checkin-head strong{font-size:18px}.checkin-head p{margin:6px 0 0;color:var(--muted);font-size:11px;line-height:1.55}.checkin-score{flex:0 0 auto;width:76px;height:76px;border-radius:50%;display:grid;place-content:center;text-align:center;background:var(--mint);color:var(--green)}.checkin-score.attention{background:var(--amber-soft);color:#9b5f24}.checkin-score strong{font:600 25px/1 Georgia}.checkin-score small{font-size:9px}.checkin-actions{display:flex;align-items:center;gap:8px;margin-top:17px}.checkin-actions button{border-radius:11px;padding:9px 13px;font-size:11px;cursor:pointer}.checkin-history{display:flex;gap:6px;align-items:end;height:32px;margin-top:15px}.checkin-history i{width:10px;min-height:4px;border-radius:4px 4px 1px 1px;background:var(--green-2)}.checkin-history-label{display:flex;justify-content:space-between;color:var(--muted);font-size:9px;margin-top:4px}.wellbeing-dialog{width:min(720px,calc(100% - 30px));max-height:min(90vh,900px)}.wellbeing-dialog form{max-height:90vh;overflow:auto}.wellbeing-questions{display:grid;gap:12px}.wellbeing-question{border:1px solid #e1e7e2;border-radius:15px;padding:13px;background:#fafbf8}.wellbeing-question label{display:block;font-size:13px;line-height:1.5}.wellbeing-question select{width:100%;margin-top:9px;border:1px solid #d4ddd8;border-radius:11px;padding:10px 12px;background:#fff;color:var(--ink);outline:none}.wellbeing-question select:focus{border-color:var(--green);box-shadow:0 0 0 3px #176b5715}.instrument-note{margin:15px 0 0;padding:11px 13px;border-radius:12px;background:#f1f5f2;color:var(--muted);font-size:10px;line-height:1.6}
.event-actions{display:grid;gap:7px}.playback-button{border:1px solid #d5cee2;border-radius:10px;background:#fbf8ff;color:#6b4d92;padding:8px 11px;font-size:11px;cursor:pointer}.playback-button:hover{background:#6b4d92;color:#fff}.playback-button:disabled{cursor:not-allowed;color:#9a92a5;background:#f5f2f7;border-color:#e7e1eb}.playback-dialog{width:min(760px,calc(100% - 30px))}.playback-dialog video{display:block;width:100%;aspect-ratio:16/9;border-radius:16px;background:#10221d}.playback-privacy{margin:12px 0;color:var(--muted);font-size:10px;line-height:1.6}.playback-fallback{display:inline-block;color:var(--green);font-size:12px;font-weight:700}
@media(max-width:900px){.wellbeing-panel{grid-template-columns:1fr}.wellbeing-intro>p:not(.eyebrow){max-width:none}}
footer a{color:var(--green);font-weight:700;text-decoration:none}footer a:hover{text-decoration:underline}
"""


DOCUMENTATION_STYLE = r"""
.docs-shell{background:linear-gradient(180deg,#f1f6f2 0,#f7f4ed 500px)}.docs-shell .topbar{position:relative}.docs-back{border:1px solid #ccd9d3;border-radius:999px;padding:9px 14px;color:var(--green);background:#fff;text-decoration:none;font-size:12px;font-weight:700}.docs-back:hover{background:var(--green);color:#fff}.docs-main{padding-top:62px}.docs-hero{max-width:870px;padding:24px 0 54px}.docs-hero h1{margin:0;font:600 clamp(48px,7vw,78px)/1.02 Georgia,"Songti SC",serif;letter-spacing:-.04em}.docs-hero h1 span{color:var(--green)}.docs-hero>p:not(.eyebrow){max-width:650px;margin:25px 0;color:var(--muted);font-size:16px;line-height:1.85}.docs-meta{display:flex;flex-wrap:wrap;gap:8px}.docs-meta span{padding:7px 10px;border:1px solid #d7e1db;border-radius:999px;background:#fff;color:var(--muted);font-size:10px}.docs-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;margin-bottom:48px;border:1px solid #dbe3dd;border-radius:24px;overflow:hidden;background:#dbe3dd}.docs-summary article{padding:25px;background:#fffefa}.docs-summary span{font:600 24px Georgia;color:#9bb4a8}.docs-summary strong{display:block;margin:12px 0 6px;font-size:15px}.docs-summary p{margin:0;color:var(--muted);font-size:11px;line-height:1.65}.docs-layout{display:grid;grid-template-columns:220px minmax(0,1fr);gap:36px;align-items:start}.docs-nav{position:sticky;top:20px;display:grid;gap:5px;padding:18px;border:1px solid #dde5df;border-radius:20px;background:#fffefa;box-shadow:var(--shadow)}.docs-nav strong{padding:4px 9px 10px;font-size:12px}.docs-nav a{padding:9px;border-radius:10px;color:var(--muted);text-decoration:none;font-size:12px}.docs-nav a:hover,.docs-nav a:focus{background:#edf6f1;color:var(--green)}.docs-content{display:grid;gap:18px}.doc-section{scroll-margin-top:20px;padding:34px;border:1px solid #e0e6e1;border-radius:25px;background:#fffefa;box-shadow:var(--shadow)}.section-number{margin:0 0 9px;color:var(--green);font-size:10px;font-weight:800;letter-spacing:.14em}.doc-section h2{margin:0 0 18px;font:600 31px/1.2 Georgia,"Songti SC",serif}.doc-section h3{margin:28px 0 10px;font-size:16px}.doc-section>p:not(.section-number){color:var(--muted);font-size:13px;line-height:1.85}.doc-section ul{margin:16px 0 0;padding-left:20px}.doc-section li{margin:9px 0;color:var(--muted);font-size:13px;line-height:1.75}.doc-section li strong{color:var(--ink)}.doc-section a{color:var(--green);font-weight:700}.doc-section code{padding:2px 6px;border-radius:6px;background:#edf3ef;color:#315a4d}.doc-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.doc-grid>div{padding:18px;border:1px solid #e4e9e5;border-radius:17px;background:#f7f9f6}.doc-grid strong{font-size:14px}.doc-grid p{margin:7px 0 0;color:var(--muted);font-size:11px;line-height:1.7}.level-table{display:grid;border:1px solid #e0e6e2;border-radius:18px;overflow:hidden}.level-table>div{display:grid;grid-template-columns:45px 110px 1fr;gap:10px;align-items:center;padding:13px 16px;border-bottom:1px solid #e7ebe8}.level-table>div:last-child{border-bottom:0}.level-table strong{font:600 22px Georgia;color:var(--green)}.level-table span{font-size:13px;font-weight:700}.level-table p{margin:0;color:var(--muted);font-size:11px;line-height:1.5}.route-flow{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}.route-flow>div{position:relative;min-height:160px;padding:16px;border-radius:17px;background:#edf5f1}.route-flow span{display:grid;width:28px;height:28px;place-items:center;border-radius:50%;background:var(--green);color:#fff;font:600 12px Georgia}.route-flow strong{display:block;margin:18px 0 7px;font-size:13px}.route-flow p{margin:0;color:var(--muted);font-size:10px;line-height:1.6}.callout{margin-top:18px!important;padding:16px 18px;border-left:3px solid var(--green);border-radius:3px 14px 14px 3px;background:#eef6f2}.docs-shell footer{margin-top:30px}
@media(max-width:900px){.docs-summary{grid-template-columns:1fr}.docs-layout{grid-template-columns:1fr}.docs-nav{position:static;display:flex;overflow:auto}.docs-nav strong{display:none}.docs-nav a{white-space:nowrap}.route-flow{grid-template-columns:1fr 1fr}.route-flow>div{min-height:135px}}
@media(max-width:560px){.docs-back{padding:8px 10px}.docs-hero h1{font-size:44px}.docs-summary{border-radius:18px}.doc-section{padding:22px;border-radius:20px}.doc-section h2{font-size:27px}.doc-grid,.route-flow{grid-template-columns:1fr}.level-table>div{grid-template-columns:35px 1fr}.level-table p{grid-column:2}}
"""


COMMON_SCRIPT = r"""
const KS_NAMES={fall:'跌倒风险',mental_wellbeing:'心理健康风险',fraud:'诈骗风险'};
const KS_ICONS={fall:'↘',mental_wellbeing:'◌',fraud:'◇'};
const KS_LABELS={0:'暂未发现',1:'需要留意',2:'建议确认',3:'优先处理',null:'暂无判断'};
const KS_REASONS={human_confirmed_fall:'家人已确认发生跌倒',fall_candidate_with_help_or_fall_speech_within_10s:'发现跌倒动作，并在 10 秒内听到求助',unrejected_fall_candidate:'发现一条需要家人确认的跌倒提醒',severe_mobility_baseline_deviation:'近期行动状态和本人平时相比变化较大',mild_or_moderate_mobility_baseline_deviation:'近期行动状态和本人平时相比有变化',qualified_pose_coverage_without_active_evidence:'今日行动记录充足，暂未发现异常',level_2_or_higher_for_three_days:'生活规律的变化已持续三天','no_personal_baseline_change_above_threshold':'日常状态与本人平时相近',who5_below_suggested_further_assessment_cutoff:'本月幸福感自评提示需要进一步关心',who5_not_below_suggested_further_assessment_cutoff:'本月幸福感自评暂未提示明显异常','daytime_presence:severe_personal_baseline_change':'日间活动规律与本人平时相比变化明显','daytime_presence:mild_personal_baseline_change':'日间活动规律与本人平时相比略有变化','activity_level:severe_personal_baseline_change':'日常活动量与本人平时相比变化明显','activity_level:mild_personal_baseline_change':'日常活动量与本人平时相比略有变化','speech_interaction:severe_personal_baseline_change':'语言互动与本人平时相比变化明显','speech_interaction:mild_personal_baseline_change':'语言互动与本人平时相比略有变化','sleep_regularity:severe_personal_baseline_change':'睡眠规律与本人平时相比变化明显','sleep_regularity:mild_personal_baseline_change':'睡眠规律与本人平时相比略有变化',high_risk_fraud_context_combination_within_30s:'短时间内听到多项需要警惕的可疑要求',two_complementary_fraud_contexts_within_30s:'同一段对话出现两类可疑要求',single_unsuppressed_suspicious_context:'环境对话中出现一项可疑要求',qualified_audio_coverage_without_active_candidate:'今日环境声音记录充足，暂未听到可疑要求'};
const KS_CATEGORIES={fall_candidate:'疑似跌倒动作',help_speech:'求助声音',fall_speech:'跌倒相关声音',credential_request:'索取账号信息',transfer_investment:'转账或投资要求',impersonation:'可疑身份声称',urgency_secrecy:'催促或保密要求',remote_control:'远程控制要求',fraud_language:'可疑对话'};
function node(tag,cls,text){const value=document.createElement(tag);if(cls)value.className=cls;if(text!==undefined)value.textContent=text;return value}
function fmtTime(value){if(!value)return '暂无';const d=new Date(value);return Number.isNaN(d.valueOf())?String(value):new Intl.DateTimeFormat('zh-CN',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(d)}
function reasonText(a){const values=(a.evidence_summary||[]).map(x=>KS_REASONS[x]||x);return values.join('；')||({insufficient_data:'日常记录还不够，暂时无法判断',data_stale:'最近没有新的家庭记录，请稍后再看',model_unavailable:'暂时无法完成判断，请稍后再看'}[a.status]||'等待更多日常记录')}
function coverageInfo(a){const c=a.data_coverage||{};if(a.domain==='fall'){const v=Number(c.qualified_pose_seconds_24h||0);return {label:`今日已观察行动 ${(v/60).toFixed(1)} / 10 分钟`,pct:Math.min(100,v/6)}}if(a.domain==='fraud'){const v=Number(c.valid_audio_seconds_24h||0);return {label:`今日已听取环境声音 ${(v/60).toFixed(1)} / 10 分钟`,pct:Math.min(100,v/6)}}const v=Number(c.eligible_distinct_days||0),req=Number(c.required_baseline_days||7),prefix=c.monthly_checkin_completed?'本月自评已纳入 · ':'本月自评待填写 · ';return {label:`${prefix}个人日常 ${v} / ${req} 天`,pct:Math.min(100,v/req*100)}}
function basisText(domain){return {fall:'结合近期行动状态与事件提醒',mental_wellbeing:'结合本人月度自评与过去 28 天日常',fraud:'来自摄像头听到的近期环境对话'}[domain]||'结合近期记录'}
function riskCard(a){const card=node('article',`risk-card risk-${a.domain}${a.score===null?' risk-null':''}`);const head=node('div','risk-card-head'),icon=node('div','domain-icon',KS_ICONS[a.domain]||'•'),state=node('div','risk-state'),label=KS_LABELS[a.score===null?'null':a.score];state.append(node('strong','',label),node('span','',a.status==='assessed'?'已更新':'暂时无法判断'));head.append(icon,state);const row=node('div','score-row'),ring=node('div','score-ring');ring.style.setProperty('--score-pct',`${a.score===null?0:Number(a.score)*25}%`);ring.append(node('strong','',a.score===null?'—':String(a.score)),node('small','',a.score===null?'': ' / 3'));const copy=node('div','score-copy');copy.append(node('strong','',KS_NAMES[a.domain]||a.domain),node('p','',a.score===null?'等待更多日常记录':`当前为 ${a.score} 级关注`));row.append(ring,copy);const why=node('p','reason',reasonText(a)),basis=node('span','risk-basis',basisText(a.domain));const info=coverageInfo(a),coverage=node('div','coverage'),line=node('div','coverage-line');line.append(node('span','',info.label),node('span','',`${Math.round(info.pct)}%`));const bar=node('div','coverage-bar'),fill=node('i');fill.style.setProperty('--coverage',`${info.pct}%`);bar.append(fill);coverage.append(line,bar);card.append(head,row,why,basis,coverage);return card}
function renderCards(assessments,target){target.textContent='';for(const a of assessments)target.append(riskCard(a))}
function renderTrends(rows,target){target.textContent='';const by={fall:[],mental_wellbeing:[],fraud:[]};for(const x of rows||[]){if(by[x.domain])by[x.domain].push(x)}const nonempty=Object.values(by).some(x=>x.length);if(!nonempty){target.append(node('div','empty','尚无历史评估。完成采集分析后，这里会按域显示最近 28 天变化。'));return}for(const domain of Object.keys(by)){const latest=new Map();for(const x of by[domain])latest.set(String(x.assessed_at).slice(0,10),x);const values=[...latest.values()].slice(-18);const row=node('div',`trend-row risk-${domain}`),label=node('div','trend-label');label.append(node('strong','',KS_NAMES[domain]),node('small','',`${values.length} 个日期`));const bars=node('div','trend-bars');for(const x of values){const b=node('i','trend-bar');b.style.setProperty('--bar-height',x.score===null?'4px':`${(Number(x.score)+.3)*23}%`);b.dataset.null=String(x.score===null);b.title=`${String(x.assessed_at).slice(0,10)} · ${x.score===null?'暂无评分':x.score+' 级'}`;bars.append(b)}row.append(label,bars);target.append(row)}const all=(rows||[]).map(x=>String(x.assessed_at).slice(0,10)).sort();if(all.length){const dates=node('div','trend-dates');dates.append(node('span','',all[0]),node('span','',all[all.length-1]));target.append(dates)}}
"""


DASHBOARD_SCRIPT = COMMON_SCRIPT + r"""
const state={snapshot:null,candidates:[],trends:[],profile:null,checkin:null,filter:'all',reviewId:null,seconds:30};
const dialog=document.getElementById('review-dialog'),note=document.getElementById('review-note'),wellbeingDialog=document.getElementById('wellbeing-dialog'),playbackDialog=document.getElementById('playback-dialog'),cloudVideo=document.getElementById('cloud-playback');
async function json(url,options){const response=await fetch(url,{cache:'no-store',...options});if(!response.ok)throw new Error(`${response.status}`);return response.json()}
function toast(message){const t=document.getElementById('toast');t.textContent=message;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2400)}
function renderProfile(){const p=state.profile||{},target=document.getElementById('profile');target.textContent='';const summary=node('div','profile-summary');summary.append(node('strong','',p.comparison_label||'与过去的自己相比'),node('p','',p.summary||'正在积累个人日常记录。'));target.append(summary);const features=node('div','profile-features'),stateText={stable:'与平时相近',slight_change:'有一点变化',significant_change:'变化较明显',unavailable:'记录不足'},directionText={higher:'比平时更多',lower:'比平时更少',stable:'与平时相近',unknown:'等待记录'};for(const x of p.features||[]){const changed=['slight_change','significant_change'].includes(x.state),d=node('div',`profile-feature${changed?' changed':''}${x.state==='unavailable'?' unavailable':''}`);d.append(node('span','',x.label),node('strong','',changed?`${stateText[x.state]} · ${directionText[x.direction]}`:stateText[x.state]||'等待记录'));features.append(d)}if(!(p.features||[]).length)features.append(node('div','empty','继续积累几天日常记录后，这里会显示与本人平时状态的比较。'));target.append(features);const badge=document.getElementById('profile-badge');badge.textContent=p.ready?'已建立':'积累中';badge.className=`status-pill ${p.ready?'good':'stale'}`}
function renderWellbeing(){const w=state.checkin||{},target=document.getElementById('wellbeing');target.textContent='';const head=node('div','checkin-head'),copy=node('div');if(w.due){copy.append(node('strong','','本月还没有填写'),node('p','','完成后会立即更新心理健康风险判断，下个月再次提醒。'));const badge=node('span','status-pill stale','本月待填写');head.append(copy,badge)}else{const current=w.current||{};copy.append(node('strong','',current.needs_attention?'近期感受值得多关心':'本月自评已完成'),node('p','',current.needs_attention?'建议和信任的家人聊一聊，必要时寻求专业支持。':`下次将在 ${w.next_reminder_date||'下月'} 提醒填写。`));const score=node('div',`checkin-score${current.needs_attention?' attention':''}`);score.append(node('strong','',String(current.percentage_score)),node('small','',' / 100'));head.append(copy,score)}target.append(head);const actions=node('div','checkin-actions'),edit=node('button','primary',w.due?'开始填写':'重新填写');edit.type='button';edit.onclick=openWellbeing;actions.append(edit);if(!w.due){const remove=node('button','secondary','删除本月记录');remove.type='button';remove.onclick=deleteWellbeing;actions.append(remove)}target.append(actions);const history=(w.history||[]).slice().reverse();if(history.length){const bars=node('div','checkin-history');for(const x of history){const b=node('i');b.style.height=`${Math.max(4,Number(x.percentage_score)*.3)}px`;b.title=`${x.month} · ${x.percentage_score}/100`;bars.append(b)}target.append(bars);const labels=node('div','checkin-history-label');labels.append(node('span','',history[0].month),node('span','',history[history.length-1].month));target.append(labels)}}
function openWellbeing(){const w=state.checkin||{},instrument=w.instrument||{},target=document.getElementById('wellbeing-questions'),answers=w.current?.answers||[];target.textContent='';(instrument.questions||[]).forEach((question,index)=>{const wrap=node('div','wellbeing-question'),label=node('label','',`${index+1}. ${question}`),select=node('select');select.dataset.index=String(index);select.setAttribute('aria-label',question);const placeholder=node('option','','请选择');placeholder.value='';select.append(placeholder);for(const option of instrument.options||[]){const item=node('option','',option.label);item.value=String(option.value);if(Number(answers[index])===Number(option.value))item.selected=true;select.append(item)}wrap.append(label,select);target.append(wrap)});wellbeingDialog.showModal()}
async function saveWellbeing(){const selects=[...document.querySelectorAll('#wellbeing-questions select')],answers=selects.map(x=>x.value===''?null:Number(x.value));if(answers.length!==5||answers.some(x=>x===null)){toast('请完成全部 5 项后再保存');return}try{await json('/api/wellbeing-checkin',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':window.KS_CSRF},body:JSON.stringify({answers})});wellbeingDialog.close();toast('本月自评已保存，风险结果已更新');await load()}catch(error){toast('暂时无法保存，请稍后重试')}}
async function deleteWellbeing(){if(!window.confirm('删除本月自评记录并重新计算心理健康风险？'))return;try{await json('/api/wellbeing-checkin',{method:'DELETE',headers:{'X-CSRF-Token':window.KS_CSRF}});toast('本月自评记录已删除');await load()}catch(error){toast('暂时无法删除，请稍后重试')}}
function reviewStatus(x){return {pending:'待确认',confirmed:'已确认',rejected:'已忽略'}[x.review_status]||x.review_status}
function renderTimeline(){const target=document.getElementById('timeline');target.textContent='';const values=state.candidates.filter(x=>state.filter==='all'||x.domain===state.filter);if(!values.length){target.append(node('div','empty',state.filter==='all'?'最近没有需要特别确认的事情。':'这一项最近没有需要确认的提醒。'));return}for(const x of values){const e=node('article',`event risk-${x.domain}`),dot=node('div','event-dot',KS_ICONS[x.domain]||'•'),body=node('div'),title=node('div','event-title');title.append(node('strong','',`${KS_NAMES[x.domain]} · ${KS_CATEGORIES[x.category]||x.category}`));const pill=node('span',`status-pill ${x.review_status==='pending'?'':x.review_status==='rejected'?'stale':'good'}`,reviewStatus(x));title.append(pill);const summary=(x.evidence_summary||[]).map(v=>KS_REASONS[v]||v).join('；')||'这条提醒需要家人看一眼';body.append(title,node('p','event-copy',`${fmtTime(x.occurred_at)} · ${summary}`));if(x.transcript_excerpt){body.append(node('div','voice-quote',x.transcript_excerpt),node('span','event-basis','由环境语音转写识别'))}if(x.archived_locally)body.append(node('span','event-basis','本机异常片段已安全归档'));if((x.reviews||[]).length){body.append(node('p','event-audit',(x.reviews||[]).map(r=>`${fmtTime(r.decided_at)} ${r.decision==='confirmed'?'已确认':'已忽略'}${r.owner_note?' · '+r.owner_note:''}`).join('；')))}e.append(dot,body);const actions=node('div','event-actions'),play=node('button','playback-button',x.playback_available?'播放异常片段':'片段暂不可用');play.type='button';play.disabled=!x.playback_available;play.title=x.playback_available?(x.playback_source==='local_archive'?'播放本机归档的事件画面和声音':'播放事件前后的云端画面和声音'):'尚无可用的本机归档或云录像';if(x.playback_available)play.onclick=()=>openPlayback(x);actions.append(play);if(x.review_status==='pending'){const b=node('button','review-button','查看并确认');b.type='button';b.onclick=()=>openReview(x);actions.append(b)}e.append(actions);target.append(e)}}
function openReview(item){state.reviewId=item.candidate_id;document.getElementById('review-title').textContent=`确认：${KS_CATEGORIES[item.category]||item.category}`;document.getElementById('review-summary').textContent=item.transcript_excerpt?`听到的内容：“${item.transcript_excerpt}”`:(item.evidence_summary||[]).map(v=>KS_REASONS[v]||v).join('；')||'请结合现场情况确认这条提醒。';note.value='';dialog.showModal();note.focus()}
async function openPlayback(item){const status=document.getElementById('playback-status'),fallback=document.getElementById('playback-fallback');document.getElementById('playback-title').textContent=`回看：${KS_CATEGORIES[item.category]||item.category}`;status.textContent=item.playback_source==='local_archive'?'正在打开本机安全归档…':'正在从云端准备事件前后的短片段…';fallback.hidden=true;fallback.removeAttribute('href');cloudVideo.removeAttribute('src');cloudVideo.load();playbackDialog.showModal();try{const payload=await json(`/api/candidates/${encodeURIComponent(item.candidate_id)}/playback`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':window.KS_CSRF},body:'{}'});cloudVideo.src=payload.url;fallback.href=payload.url;fallback.hidden=false;status.textContent=`${fmtTime(payload.started_at)} 至 ${fmtTime(payload.ended_at)} · ${payload.source==='local_archive'?'本机安全归档':'临时云端地址'}`;cloudVideo.load();cloudVideo.play().catch(()=>{})}catch(error){status.textContent='暂时无法取得异常片段，请检查本机归档或云录像回放状态。'}}
async function submitReview(decision){if(!state.reviewId)return;try{await json(`/api/candidates/${encodeURIComponent(state.reviewId)}/review`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':window.KS_CSRF},body:JSON.stringify({decision,operator:'local_owner',owner_note:note.value.trim()||null})});dialog.close();toast(decision==='confirmed'?'已保存您的确认':'已忽略这条提醒');await load()}catch(error){toast('暂时无法保存，请稍后重试')}}
async function load(){document.getElementById('refresh-button').disabled=true;try{const payload=await json('/api/dashboard'),s=payload.snapshot||{};state.snapshot=s;state.candidates=payload.candidates||[];state.trends=payload.trends||[];state.profile=payload.profile||{};state.checkin=payload.wellbeing_checkin||{};renderCards(s.assessments||[],document.getElementById('cards'));renderTrends(state.trends,document.getElementById('trends'));renderProfile();renderWellbeing();renderTimeline();document.getElementById('generated-at').textContent=`${fmtTime(s.generated_at)} 更新`;state.seconds=30}catch(error){toast('暂时无法读取最新记录，请稍后重试')}finally{document.getElementById('refresh-button').disabled=false}}
for(const b of document.querySelectorAll('.filter'))b.onclick=()=>{state.filter=b.dataset.domain;for(const x of document.querySelectorAll('.filter'))x.classList.toggle('active',x===b);renderTimeline()};
document.getElementById('refresh-button').onclick=load;document.getElementById('confirm-button').onclick=()=>submitReview('confirmed');document.getElementById('reject-button').onclick=()=>submitReview('rejected');document.getElementById('save-wellbeing-button').onclick=saveWellbeing;
playbackDialog.addEventListener('close',()=>{cloudVideo.pause();cloudVideo.removeAttribute('src');cloudVideo.load();document.getElementById('playback-fallback').removeAttribute('href')});cloudVideo.addEventListener('error',()=>{document.getElementById('playback-status').textContent='当前浏览器无法直接播放该片段，可尝试下方的新窗口回看。'});
setInterval(()=>{state.seconds-=1;if(state.seconds<=0)load();document.getElementById('refresh-copy').textContent=`${state.seconds} 秒后自动刷新`},1000);load();
"""


OFFLINE_SCRIPT = COMMON_SCRIPT + r"""
const payload=JSON.parse(document.getElementById('payload').textContent),snapshot=payload.snapshot||payload;
renderCards(snapshot.assessments||[],document.getElementById('cards'));renderTrends(payload.trends||[],document.getElementById('trends'));
const quality=document.getElementById('quality'),fresh=snapshot.data_freshness||{};for(const [a,b,c] of [['报告内容','三项独立关注','行动、日常规律和可疑对话分别查看'],['查看范围',payload.visibility==='public_evidence'?'安心分享版':'家庭照护版',payload.visibility==='public_evidence'?'已隐藏身份、备注和具体事件':'保留照护者需要的确认记录'],['记录状态',fresh.stale?'需要新的日常记录':'最近已更新','以报告生成时的家庭记录为准'],['阅读方式','每一项单独看','不会把三项合成一个笼统分数']]){const d=node('div','quality-item');d.append(node('span','',a),node('strong','',b),node('small','',c));quality.append(d)}
const timeline=document.getElementById('timeline'),events=snapshot.timeline||[];if(!events.length){timeline.append(node('div','empty','最近没有需要特别留意的事情。'))}else{for(const x of events){const e=node('article',`event risk-${x.domain}`),dot=node('div','event-dot',KS_ICONS[x.domain]||'•'),body=node('div'),title=node('div','event-title');title.append(node('strong','',`${KS_NAMES[x.domain]} · ${KS_CATEGORIES[x.category]||x.category}`));body.append(title,node('p','event-copy',`${fmtTime(x.occurred_at)} · ${(x.evidence_summary||[]).map(v=>KS_REASONS[v]||v).join('；')}`));if(x.transcript_excerpt)body.append(node('div','voice-quote',x.transcript_excerpt),node('span','event-basis','由环境语音转写识别'));e.append(dot,body);timeline.append(e)}}
"""


OFFLINE_PUBLIC_SCRIPT = COMMON_SCRIPT + r"""
const payload=JSON.parse(document.getElementById('payload').textContent),snapshot=payload;
renderCards(snapshot.assessments||[],document.getElementById('cards'));renderTrends(payload.trends||[],document.getElementById('trends'));
const quality=document.getElementById('quality');for(const [a,b,c] of [['报告内容','三项独立关注','行动、日常规律和可疑对话分别查看'],['查看范围','安心分享版','已隐藏身份、照护备注和具体事件'],['记录状态',snapshot.data_freshness?.stale?'需要新的日常记录':'最近已更新','以报告生成时的家庭记录为准'],['阅读方式','每一项单独看','不会把三项合成一个笼统分数']]){const d=node('div','quality-item');d.append(node('span','',a),node('strong','',b),node('small','',c));quality.append(d)}
document.getElementById('timeline').append(node('div','empty','安心分享版不会展示具体对话、事件时间和照护备注。'));
"""
