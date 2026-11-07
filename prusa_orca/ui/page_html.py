"""HTML for the Prusa tab, laid out like Orca's Device tab: side tabs, camera, progress and controls."""

from .icons import printer_image_html

PAGES_HTML = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  /* Tokens of Orca's own dialogs (resources/web/dialog/css/theme.css, include/global.css), keyed on the
     data-orca-theme attribute Orca sets on plugin pages. */
  :root { --acc: var(--orca-accent, #009688); --acc-hover: #26a69a; --bd: var(--orca-border, #ddd); --mu: var(--orca-muted, #888);
          --panel: rgba(127,127,127,.06); --prusa: #fa6831;
          --row-hover: #f7f9fb; --row-selected: #eaf2ff; --control-bd: #b8b8b8; --info: #00897b; --info-bg: rgba(0,137,123,.12);
          --btn-bg: #dfdfdf; --btn-hover: #d4d4d4; --btn-fg: #262e30; --btn-fg-disabled: #6b6b6b; --btn-alert: #e14747;
          --ok: #137333; --ok-bg: rgba(19,115,51,.14); --warn: #a15c00; --warn-bg: rgba(199,122,22,.14);
          --danger: #b42318; --danger-bg: rgba(180,35,24,.14); }
  :root[data-orca-theme="dark"] { --bd: #4a4a51; --control-bd: #5a5a62; --info: #5eead4; --info-bg: rgba(0,150,136,.18); --acc-hover: #008172; --row-hover: #2b3340; --row-selected: #244945;
          --btn-bg: #3e3e45; --btn-hover: #4d4d54; --btn-fg: #efeff0; --btn-fg-disabled: #818183;
          --ok: #37c871; --ok-bg: rgba(55,200,113,.16); --warn: #f0b45a; --warn-bg: rgba(240,180,90,.18);
          --danger: #ff7b72; --danger-bg: rgba(255,123,114,.16); }
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; font-size: 13px; font-family: var(--orca-font, system-ui); }
  /* Form controls don't inherit the page font by default. */
  input, select, textarea, button { font-family: inherit; }
  small { font-size: 12px; }
  body { display: flex; overflow: hidden; }
  nav { width: 200px; flex: none; border-right: 1px solid var(--bd); display: flex; flex-direction: column; }
  nav .printer { padding: 14px 16px; border-bottom: 1px solid var(--bd); }
  nav .printer b { display: block; font-size: 15px; margin-top: 8px; }
  nav .printer .pic { color: var(--mu); }
  nav .printer .pic svg { width: 120px; height: 90px; display: block; margin: 0 auto; }
  nav .printer .pic .art { width: 128px; height: auto; display: block; margin: 0 auto; filter: drop-shadow(0 0 1px rgba(255,255,255,.25)); }
  nav .printer { border-top: 3px solid var(--prusa); }
  nav button.tab.on svg { stroke: var(--prusa); }
  nav .printer small { color: var(--mu); }
  nav button.tab { all: unset; cursor: pointer; padding: 12px 16px; display: flex; gap: 10px; align-items: center; border-left: 3px solid transparent; }
  nav button.tab:hover { background: var(--panel); }
  nav button.tab.on { border-left-color: var(--acc); background: var(--panel); font-weight: 600; }
  nav svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 1.8; }
  nav .foot { margin-top: auto; padding: 10px 16px; color: var(--mu); font-size: 11px; }
  nav .ready { margin: 14px 16px 0; padding-top: 12px; border-top: 1px solid var(--bd); display: none; }
  nav .ready small { display: block; color: var(--mu); margin-bottom: 6px; }
  nav .ready button { width: 100%; }
  main { flex: 1; overflow: auto; }
  .page { display: none; padding: 12px; gap: 12px; min-height: 100%; }
  .page.on { display: flex; }
  .col { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
  .box { border: 1px solid var(--bd); border-radius: 8px; overflow: hidden; }
  /* Orca dialog buttons: grey by default, accent for the primary action, red on hover for destructive ones. */
  button:not(.tab):not(.icon) { height: 32px; padding: 0 13px; border: 0; border-radius: 4px; font-size: 13px; line-height: 32px;
           background: var(--btn-bg); color: var(--btn-fg); cursor: pointer; white-space: nowrap; }
  button:not(.tab):not(.icon):hover { background: var(--btn-hover); filter: none; }
  button.primary:not(.tab):not(.icon) { background: var(--acc); color: #fefefe; }
  button.primary:not(.tab):not(.icon):hover { background: var(--acc-hover); }
  button.danger:not(.tab):not(.icon):hover { background: var(--btn-alert); color: #fefefe; }
  button:not(.tab):not(.icon):disabled { background: var(--btn-bg); color: var(--btn-fg-disabled); opacity: 1; cursor: default; }
  .box > h4 button:not(.tab) { height: 26px; line-height: 26px; padding: 0 10px; }
  input[type=checkbox] { -webkit-appearance: none; appearance: none; width: 14px; height: 14px; margin: 0; padding: 0;
           border: 1px solid var(--control-bd); border-radius: 2px; background: var(--orca-bg, #fff); display: inline-grid; place-content: center;
           vertical-align: middle; cursor: pointer; }
  input[type=checkbox]::before { content: ""; width: 10px; height: 10px; transform: scale(0); box-shadow: inset 1em 1em #fff;
           clip-path: polygon(7% 37%, 0 45%, 33% 78%, 100% 30%, 95% 21%, 33% 64%); }
  input[type=checkbox]:checked { background: var(--acc); border-color: var(--acc); }
  input[type=checkbox]:checked::before { transform: scale(1); }
  input[type=text], input[type=password], input[type=number], select { height: 30px; border-radius: 4px; border-color: var(--control-bd); }
  input[type=text]:focus, input[type=password]:focus, input[type=number]:focus, select:focus { border-color: var(--acc); }
  /* The open list is drawn natively from these; without them it can come out white in dark mode. */
  select, option, optgroup { background-color: var(--orca-bg, #fff); color: var(--orca-fg, #262e30); }
  option:checked { background-color: var(--row-selected); }
  .box > h4 { margin: 0; padding: 8px 12px; font-size: 13px; border-bottom: 1px solid var(--bd); display: flex; justify-content: space-between; align-items: center; }
  .box > h4 small { font-weight: normal; color: var(--mu); }
  .box > h4 { justify-content: flex-start; }
  .box > h4::before { content: ""; flex: none; width: 3px; height: 12px; background: var(--prusa); border-radius: 2px; margin-right: 8px; }
  .box > h4 > small, .box > h4 > span { margin-left: auto; }
  .pad { padding: 12px; }
  .camwrap { flex: 1; display: flex; flex-direction: column; }
  .cam { background: #000; flex: 1; min-height: 240px; max-height: 62vh; display: flex; align-items: center; justify-content: center; color: #aaa; position: relative; }
  .cam img { width: 100%; height: 100%; object-fit: contain; }
  .cam img:not([src]) { display: none; }
  .cam .empty { display: flex; flex-direction: column; align-items: center; gap: 8px; }
  .cam .empty svg { width: 48px; height: 48px; fill: none; stroke: #777; stroke-width: 1.5; }
  .cam .tag { position: absolute; left: 8px; bottom: 6px; font-size: 11px; color: #ddd; background: rgba(0,0,0,.5); padding: 1px 6px; border-radius: 3px; }
  .cam .hint { position: absolute; left: 8px; right: 8px; top: 8px; display: none; padding: 6px 10px; border-radius: 4px; color: #fff; background: rgba(161,92,0,.85); font-size: 12px; }
  .job { display: flex; gap: 14px; align-items: center; }
  .thumb { width: 96px; height: 96px; flex: none; border: 1px solid var(--bd); border-radius: 4px; background: var(--panel) center/contain no-repeat;
           display: flex; align-items: center; justify-content: center; }
  .thumb svg { width: 40px; height: 40px; fill: none; stroke: var(--mu); stroke-width: 1.4; }
  .thumb.has svg { display: none; }
  .job .info { flex: 1; min-width: 0; }
  .job .name { font-size: 14px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .bar { height: 8px; border-radius: 4px; background: var(--panel); border: 1px solid var(--bd); margin: 8px 0 6px; overflow: hidden; }
  .bar i { display: block; height: 100%; width: 0; background: var(--acc); transition: width .5s; }
  .meta { display: flex; gap: 18px; color: var(--mu); align-items: baseline; }

  .meta b { color: var(--orca-fg, inherit); font-size: 18px; font-weight: 600; margin-right: 2px; }
  .ctl { display: flex; gap: 6px; }
  .icon { all: unset; cursor: pointer; width: 34px; height: 34px; border-radius: 50%; border: 1px solid var(--bd); display: flex; align-items: center; justify-content: center; }
  .icon:hover { border-color: var(--acc); }
  .icon svg { width: 16px; height: 16px; fill: currentColor; }
  .icon.stop svg { fill: #d9534f; }
  .temps { display: grid; grid-template-columns: repeat(4, 1fr); }
  .temps .set.editing { background: var(--row-selected); }
  .setter { display: none; flex-wrap: wrap; gap: 8px; align-items: center; padding: 10px 12px; border-top: 1px solid var(--bd); }
  .setter.on { display: flex; }
  .setter input[type=range] { flex: 1; min-width: 140px; accent-color: var(--acc); }
  .setter input[type=number] { width: 70px; text-align: right; }
  .setter .presets { display: flex; gap: 4px; }
  .setter .presets button:not(.tab) { height: 26px; line-height: 26px; padding: 0 8px; }
  .temps div { padding: 10px; text-align: center; border-right: 1px solid var(--bd); }
  .temps div:last-child { border-right: 0; }
  .temps svg { width: 22px; height: 22px; fill: none; stroke: var(--mu); stroke-width: 1.6; display: block; margin: 0 auto 4px; }
  .temps div { padding: 16px 10px; }
  .temps b { font-size: 20px; white-space: nowrap; } .temps small { color: var(--mu); display: block; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .temps div { min-width: 0; }
  .temps > div:nth-child(n+5) { border-top: 1px solid var(--bd); }
  .temps > div:nth-child(4n) { border-right: 0; }
  .tools { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; padding: 12px; }
  .tool small, .tool .temp { overflow: hidden; text-overflow: ellipsis; }
  .tool .temp { white-space: nowrap; }
  .tool { text-align: center; padding: 10px 4px; border-radius: 6px; border: 1px solid var(--bd); }
  .tool.on { border: 2px solid var(--acc); background: var(--panel); }
  .tool.on .t::after { content: " ●"; color: var(--acc); }
  .spool { width: 52px; height: 72px; margin: 4px auto; border-radius: 6px; border: 1px solid var(--bd); position: relative; overflow: hidden; }
  .spool::after { content: ""; position: absolute; left: 50%; top: 50%; width: 12px; height: 12px; margin: -6px; border-radius: 50%; background: rgba(255,255,255,.5); }
  .spool.none { background: repeating-linear-gradient(45deg, transparent 0 6px, var(--panel) 6px 12px); }
  .tool .t { font-weight: 600; } .tool small { display: block; color: var(--mu); font-size: 12px; line-height: 1.35; }
  .tool .temp { font-size: 12px; margin-top: 4px; }
  .tool .txt { min-height: 34px; }
  .tools.assign .tool { display: flex; flex-direction: column; }
  .tools.assign select { margin-top: auto !important; }
  .msg { color: var(--mu); min-height: 1em; padding: 0 12px 10px; }
  table { width: 100%; border-collapse: collapse; }
  .cat-bar { display: flex; gap: 8px; align-items: center; }
  .cat-bar input { flex: 1; } .cat-bar select { width: 140px; }
  .cat-filters { margin-top: 8px; } .cat-filters select { flex: 1; width: auto; min-width: 0; }
  #cat-notice { display: none; margin-top: 8px; padding: 6px 10px; border: 1px solid var(--warn); border-radius: 6px; color: var(--warn); background: var(--warn-bg); }
  #cat-list { max-height: 420px; overflow: auto; margin-top: 8px; }
  #cat-list .brand { font-weight: 600; padding: 8px 0 4px; border-bottom: 1px solid var(--bd); }
  #cat-list .row { display: flex; gap: 8px; align-items: center; padding: 5px 0; border-bottom: 1px solid var(--bd); }
  #cat-list .row .nm { flex: 1; min-width: 0; }
  #cat-list .row small { color: var(--mu); margin-left: 8px; }
  #cat-list .row button { padding: 2px 8px; }
  #cat-list .row .src { display: flex; gap: 4px; flex: none; margin-left: auto; }
  #cat-list .row .src svg { display: block; }
  td, th { text-align: left; padding: 4px 10px; border-bottom: 1px solid var(--bd); vertical-align: middle; height: 34px; }
  th { color: inherit; font-weight: 600; font-size: 12px; height: auto; padding: 8px 10px; }
  tbody tr { cursor: pointer; }
  tbody tr:hover { background: var(--row-hover); }
  tr.sel, tr.sel:hover { background: var(--row-selected); outline: 1px solid var(--acc); outline-offset: -1px; }
  td.num { color: var(--mu); white-space: nowrap; width: 1%; }
  .fthumb { width: 36px; height: 36px; border-radius: 4px; border: 1px solid var(--bd); background: var(--panel) center/contain no-repeat; }
  label { display: block; margin: 10px 0 3px; color: var(--mu); }
  input[type=text], input[type=password], select { width: 100%; padding: 5px; }
  .btns { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
  .pill { font-size: 11px; padding: 1px 8px; border-radius: 9px; border: 1px solid var(--bd); }
  .ok { border-color: var(--ok); color: var(--ok); background: var(--ok-bg); } .bad { border-color: var(--danger); color: var(--danger); background: var(--danger-bg); }
  .grid2 { display: grid; grid-template-columns: repeat(2, minmax(0, 380px)); gap: 0 32px; }
  .kv { display: grid; grid-template-columns: 140px 1fr; gap: 6px 10px; }
  .kv > span:nth-child(odd) { color: var(--mu); }
  #busy { position: fixed; top: 0; left: 200px; right: 0; z-index: 9; display: none; }
  #busy.on { display: block; }
  #busy .track { height: 4px; overflow: hidden; background: rgba(127,127,127,.15); }
  #busy .track i { display: block; height: 100%; width: 30%; background: var(--acc); animation: slide 1.1s ease-in-out infinite; }
  #busy.slow .track i { background: #d08b00; }
  @keyframes slide { 0% { margin-left: -30%; } 100% { margin-left: 100%; } }
  #busy .label { float: right; margin: 4px 10px 0 0; font-size: 11px; padding: 2px 8px; border-radius: 9px;
                 background: var(--orca-bg, #fff); border: 1px solid var(--bd); color: var(--mu); }
  #busy.slow .label { color: #d08b00; border-color: #d08b00; }
  #cloud-warn { display: none; margin: 12px 12px 0; padding: 8px 12px; border: 1px solid var(--warn); border-radius: 6px; color: var(--warn); background: var(--warn-bg); }
  body.busy #cloud-warn { margin-top: 36px; }
  .banner { display: none; margin: 12px 12px 0; padding: 8px 12px; border: 1px solid; border-radius: 6px; }
  #identity-error { border-color: var(--danger); color: var(--danger); background: var(--danger-bg); font-weight: 600; }
  #preset-notice { border-color: var(--warn); background: var(--warn-bg); color: inherit; }
  #mc .wbox { min-height: 0; overflow-x: hidden; }
  #mc button.opt { display: block; width: 100%; height: auto; line-height: 1.35; white-space: normal; text-align: left; margin-top: 8px; padding: 8px 12px; }
  #mc .opt small { display: block; color: var(--mu); font-weight: normal; margin-top: 2px; }
  #mc .opt.primary small { color: rgba(255,255,255,.85); }
  .tool .swap { color: var(--warn); }
  #pick-slot { flex: 1; min-height: 0; display: flex; flex-direction: column; }
  #pick #cat-box { border: 0; border-radius: 0; flex: 1; min-height: 0; display: flex; flex-direction: column; }
  #pick #cat-box > .pad { flex: 1; min-height: 0; display: flex; flex-direction: column; }
  #pick #cat-list { flex: 1; min-height: 0; max-height: none; overflow-y: auto; }
  #pick .wnav { margin: 0; padding: 10px 12px; border-top: 1px solid var(--bd); }
  #cat-list .row.pickable { cursor: pointer; padding-left: 6px; border-radius: 4px; user-select: none; -webkit-user-select: none; }
  #cat-list .row.pickable:hover { background: var(--row-hover); }
  #cat-list .row.picked { background: var(--row-selected); }
  .tools:not(.assign) .tool { cursor: pointer; } .tools:not(.assign) .tool:hover { background: var(--panel); }
  #wiz, #mc, #pick { display: none; position: fixed; inset: 0; z-index: 20; background: rgba(0,0,0,.6); align-items: center; justify-content: center; }
  #wiz .wbox { min-height: 340px; display: flex; flex-direction: column; } #wiz .wnav { margin-top: auto; padding-top: 18px; }
  #wiz.on, #mc.on, #pick.on { display: flex; }
  #mc { z-index: 21; }
  #wiz .wbox, #mc .wbox, #pick .wbox { width: min(620px, 92vw); max-height: 88vh; overflow: auto; background: var(--orca-bg, #fff); color: var(--orca-fg, inherit);
               border: 1px solid var(--bd); border-radius: 8px; padding: 18px 22px; box-shadow: 0 10px 28px rgba(0,0,0,.3); }
  #pick .wbox { width: min(760px, 94vw); height: 80vh; min-height: 0; display: flex; flex-direction: column; padding: 0; overflow: hidden; }
  #wiz h3 { margin: 0 0 12px; }
  .wsteps { display: flex; gap: 6px; list-style: none; padding: 0; margin: 0 0 14px; counter-reset: s; }
  .wsteps li { flex: 1; font-size: 12px; color: var(--mu); border-top: 3px solid var(--bd); padding-top: 4px; counter-increment: s; }
  .wsteps li::before { content: counter(s) ". "; }
  .wsteps li.on { color: inherit; font-weight: 600; border-top-color: var(--acc); }
  .wsteps li.done { border-top-color: var(--acc); }
  .wpane { display: none; } .wpane.on { display: block; }
  .how { padding-left: 20px; margin: 8px 0; line-height: 1.5; }
  .alt { color: var(--mu); margin-top: 14px; } .alt a { color: var(--acc); }
  .wlist { display: flex; flex-direction: column; gap: 6px; }
  .wlist button:not(.tab):not(.icon) { text-align: left; height: auto; line-height: 1.4; padding: 10px 36px 10px 12px; position: relative;
           background: transparent; border: 1px solid var(--bd); }
  .wlist button:not(.tab):not(.icon):hover { border-color: var(--acc); background: var(--row-hover); }
  .wlist button::after { content: "\203A"; position: absolute; right: 14px; top: 50%; transform: translateY(-50%); font-size: 20px; color: var(--mu); }
  .wlist button small { display: block; color: var(--mu); }
  .wsteps li.on { color: inherit; font-weight: 700; }
  .wnote { color: var(--mu); font-size: 12px; }
  .wfound { padding-left: 20px; line-height: 1.6; }
  .wfound li::marker { content: "✓  "; color: var(--ok); }
  #w-missing p { background: var(--warn-bg); border: 1px solid var(--warn); border-radius: 6px; padding: 8px 12px; }
  #w-result.ok { color: var(--ok); } #w-result.bad { color: var(--danger); }
  .wnav { margin-top: 18px; }
  .waiting { opacity: .5; pointer-events: none; position: relative; }
  .waiting::after { content: ""; position: absolute; top: 6px; right: 6px; width: 10px; height: 10px; border-radius: 50%;
                    border: 2px solid var(--acc); border-right-color: transparent; animation: spin .8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .tools:empty::before { content: "No tool data yet."; color: var(--mu); grid-column: 1 / -1; }
  #toast { position: fixed; right: 16px; bottom: 16px; max-width: 460px; padding: 10px 14px; border-radius: 6px; background: #333; color: #fff;
           box-shadow: 0 4px 14px rgba(0,0,0,.25); opacity: 0; transition: opacity .3s; pointer-events: none; z-index: 10; white-space: pre-line; }
  #toast.on { opacity: .95; }
  .res { font-size: 11px; padding: 1px 8px; border-radius: 9px; border: 1px solid; white-space: nowrap; font-weight: normal; }
  .kv .res { justify-self: start; }
  .res.finished { color: var(--ok); background: var(--ok-bg); }
  .res.printing, .res.sending, .res.uploaded { color: var(--info); background: var(--info-bg); }
  .res.stopped, .res.paused, .res.attention, .res.not_started, .res.unknown, .res.replaced { color: var(--warn); background: var(--warn-bg); }
  .res.failed, .res.send_failed { color: var(--danger); background: var(--danger-bg); }
  .shot { width: 150px; border-radius: 4px; border: 1px solid var(--bd); }
  .shot-cap { font-size: 11px; color: var(--mu); text-align: center; }
  .temps .set { cursor: pointer; border-radius: 4px; }
  .temps .set:hover { background: var(--panel); }
  .temps .set.off { cursor: default; } .temps .set.off:hover { background: none; }
  .jog { display: flex; gap: 24px; padding: 14px 12px; align-items: center; justify-content: center; border-top: 1px solid var(--bd); }
  .pad3 { display: grid; grid-template-columns: repeat(3, 40px); grid-template-rows: repeat(3, 40px); gap: 4px; }
  .pad3 button, .zcol button { all: unset; height: auto !important; padding: 0 !important; line-height: normal !important; cursor: pointer; border: 1px solid rgba(127,127,127,.35); background: rgba(127,127,127,.12); border-radius: 6px;
    display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; }
  .pad3 button:hover, .zcol button:hover { border-color: var(--acc); color: var(--acc); }
  .pad3 button:disabled, .zcol button:disabled { opacity: .35; cursor: default; }
  .zcol { display: grid; grid-template-rows: repeat(3, 40px); gap: 4px; width: 56px; }
  .steps { display: flex; gap: 4px; }
  .steps button { padding: 0 8px !important; min-width: 0; height: 24px !important; line-height: 22px !important; }
  .steps button { background: transparent !important; color: inherit !important; border: 1px solid rgba(127,127,127,.35) !important; border-radius: 4px; }
  .steps button.on { background: var(--acc) !important; color: #fff !important; border-color: var(--acc) !important; }
</style></head>
<body>
<nav>
  <div class="printer"><div class="pic">__PRINTER_SVG__</div><b id="title">Prusa printer</b><small><span id="conn" class="pill bad">offline</span> <span id="phase">-</span></small></div>
  <button class="tab on" data-page="status"><svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/></svg>Status</button>
  <button class="tab" data-page="files"><svg viewBox="0 0 24 24"><path d="M4 4h10l6 6v10H4z"/><path d="M14 4v6h6"/></svg>Storage</button>
  <button class="tab" data-page="filament"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2.5"/></svg>Filament</button>
  <button class="tab" data-page="history"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3 2"/></svg>History</button>
  <button class="tab" data-page="settings"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/></svg>Settings</button>
  <div class="ready" id="ready"><small id="ready-note"></small><button id="b-ready"></button></div>
  <div class="foot" id="foot">-</div>
</nav>
<main>
  <div id="cloud-warn"></div>
  <div id="identity-error" class="banner"></div>
  <div id="preset-notice" class="banner"></div>
  <section class="page on" id="p-status">
    <div class="col" style="flex: 1.6">
      <div class="box camwrap">
        <h4>Camera <small id="cam-age"></small></h4>
        <div class="cam"><img id="cam" alt="">
          <div class="empty" id="cam-empty"><svg viewBox="0 0 24 24"><path d="M3 7h4l2-3h6l2 3h4v13H3z"/><circle cx="12" cy="13" r="4"/></svg>Waiting for the camera…</div>
          <span class="tag" id="cam-tag" style="display:none"></span><div class="hint" id="cam-hint"></div></div>
      </div>
      <div class="box">
        <h4>Printing progress</h4>
        <div class="pad job">
          <div class="thumb" id="thumb"><svg viewBox="0 0 24 24"><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M4 7.5l8 4.5 8-4.5M12 12v9"/></svg></div>
          <div class="info">
            <div class="name" id="job-name">No job</div>
            <div class="bar"><i id="job-bar"></i></div>
            <div class="meta"><span><b id="job-pct">-</b>%</span><span id="job-layer">Layer: -</span><span id="job-left">-</span></div>
          </div>
          <div class="ctl">
            <button class="icon" id="b-pause" title="Pause"><svg viewBox="0 0 24 24"><rect x="6" y="5" width="4" height="14"/><rect x="14" y="5" width="4" height="14"/></svg></button>
            <button class="icon" id="b-resume" title="Resume"><svg viewBox="0 0 24 24"><path d="M7 5v14l12-7z"/></svg></button>
            <button class="icon stop" id="b-stop" title="Stop"><svg viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="1"/></svg></button>
          </div>
        </div>
        <div class="msg" id="msg"></div>
      </div>
    </div>
    <div class="col" style="flex: 1">
      <div class="box">
        <h4>Control</h4>
        <div class="temps">
          <div class="set" data-cmd="SET_NOZZLE_TEMPERATURE" data-arg="nozzle_temperature" data-min="0" data-max="290" data-step="5" data-presets="0,215,240,260" title="Set the active tool's temperature"><svg viewBox="0 0 24 24"><path d="M8 3h8v6l-4 5-4-5z"/><path d="M12 14v6"/></svg><b id="t-noz">-</b><small id="t-noz-t">Nozzle</small></div>
          <div class="set" data-cmd="SET_HEATBED_TEMPERATURE" data-arg="bed_temperature" data-min="0" data-max="120" data-step="5" data-presets="0,60,80,100" title="Set the bed temperature"><svg viewBox="0 0 24 24"><rect x="3" y="14" width="18" height="4" rx="1"/><path d="M7 11c1-2-1-3 0-5M12 11c1-2-1-3 0-5M17 11c1-2-1-3 0-5"/></svg><b id="t-bed">-</b><small id="t-bed-t">Bed</small></div>
          <div><svg viewBox="0 0 24 24"><path d="M12 3v18M5 8l7-5 7 5"/></svg><b id="t-z">-</b><small>Z height</small></div>
          <div title="The tool the printer has picked up"><svg viewBox="0 0 24 24"><path d="M7 3h10v7l-5 6-5-6z"/><path d="M12 16v5"/></svg><b id="t-tool">-</b><small>Active tool</small></div>
          <div><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="2"/><path d="M12 10c0-4 1-7 4-7 0 3-2 5-4 7zM14 12c4 0 7 1 7 4-3 0-5-2-7-4zM12 14c0 4-1 7-4 7 0-3 2-5 4-7zM10 12c-4 0-7-1-7-4 3 0 5 2 7 4z"/></svg><b id="t-fan">-</b><small>Part fan</small></div>
          <div><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="2"/><path d="M12 10c0-4 1-7 4-7 0 3-2 5-4 7zM14 12c4 0 7 1 7 4-3 0-5-2-7-4zM12 14c0 4-1 7-4 7 0-3 2-5 4-7zM10 12c-4 0-7-1-7-4 3 0 5 2 7 4z"/></svg><b id="t-hfan">-</b><small>Hotend fan</small></div>
          <div class="set" data-cmd="SET_SPEED" data-arg="speed" data-min="10" data-max="300" data-step="5" data-presets="50,100,150,200" title="Set the print speed"><svg viewBox="0 0 24 24"><path d="M4 18l5-6 4 4 7-9"/><path d="M15 7h5v5"/></svg><b id="t-speed">-</b><small>Speed</small></div>
          <div class="set" data-cmd="SET_FLOW" data-arg="flow" data-min="10" data-max="150" data-step="1" data-presets="90,95,100,105" title="Set the print flow"><svg viewBox="0 0 24 24"><path d="M12 3c3 5 6 8 6 12a6 6 0 0 1-12 0c0-4 3-7 6-12z"/></svg><b id="t-flow">-</b><small>Flow</small></div>
        </div>
        <div class="setter" id="setter">
          <b id="setter-label"></b>
          <input type="range" id="setter-range">
          <input type="number" id="setter-num"><span id="setter-unit"></span>
          <span class="presets" id="setter-presets"></span>
          <button class="primary" id="setter-set">Set</button><button id="setter-close">Cancel</button>
        </div>
        <div class="jog" id="jog">
          <div class="pad3">
            <span></span><button data-move="y" data-dir="1" title="Y+">Y+</button><span></span>
            <button data-move="x" data-dir="-1" title="X-">X−</button>
            <button id="b-home" title="Home all axes"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 11l8-7 8 7v9H4z"/><path d="M10 20v-6h4v6"/></svg></button>
            <button data-move="x" data-dir="1" title="X+">X+</button>
            <span></span><button data-move="y" data-dir="-1" title="Y-">Y−</button><span></span>
          </div>
          <div style="display:flex; gap: 14px; align-items: center">
            <div class="zcol"><button data-move="z" data-dir="1" title="Bed down (Z+)">Z+</button><span style="text-align:center;color:var(--mu);align-self:center">Z</span><button data-move="z" data-dir="-1" title="Bed up (Z-)">Z−</button></div>
            <div><small style="color:var(--mu)">Step (mm)</small><div class="steps" id="steps"><button>0.1</button><button class="on">1</button><button>10</button><button>50</button></div>
              <div class="btns" style="margin-top:8px"><button id="b-motion" title="Allow manual movement">Enable movement</button><button id="b-motors" class="danger" title="Turn the stepper motors off">Motors off</button></div></div>
          </div>
        </div>
        <div class="msg" id="ctl-why"></div>
        <div class="pad kv" id="extras" style="display:none; border-top: 1px solid var(--bd); grid-template-columns: 1fr auto"></div>
      </div>
      <div class="box">
        <h4>Tools</h4>
        <div class="tools" id="tools"></div>
      </div>
      <div class="box">
        <h4>Printer</h4>
        <div class="pad kv">
          <span>State</span><span id="st-state">-</span>
          <span>Model</span><span id="st-model">-</span>
          <span>Firmware</span><span id="st-fw">-</span>
          <span>Address</span><span id="st-ip">-</span>
          <span>Printing for</span><span id="st-time">-</span>
        </div>
      </div>
    </div>
  </section>

  <section class="page" id="p-files" style="flex-direction: column">
    <div class="box">
      <h4>Printer storage <span><button id="b-files">Refresh</button> <button id="b-print" class="primary">Print selected</button></span></h4>
      <table><thead><tr><th></th><th>Name</th><th>Uploaded</th></tr></thead><tbody id="files"></tbody></table>
    </div>
  </section>

  <section class="page" id="p-filament" style="flex-direction: column">
    <div class="box">
      <h4>Filament per tool</h4>
      <div class="tools assign" id="tools-assign"></div>
      <div class="pad" style="padding-top:0;color:var(--mu)">Choosing a filament sets it for slicing and records it on the tool in Prusa Connect. It does not load or move filament.</div>
    </div>
    <div class="box"><h4>Sync with the slicer's filament slots</h4>
      <table><thead><tr><th><input type="checkbox" id="fs-all" title="Select all"></th><th>Tool</th><th>Printer</th><th>Slicer slot</th><th></th></tr></thead><tbody id="fsync"></tbody></table>
      <div class="pad">
        <div class="btns" style="margin-top:0"><button id="b-fs-orca">Printer → Slicer</button><button id="b-fs-printer">Slicer → Printer</button></div>
        <label style="display:flex; gap:6px; align-items:center; margin:10px 0 0; color:inherit" title="When a filament is loaded on the printer, set the matching preset in its slicer slot without asking. Skipped when the slot holds one of your own presets of the same material."><input type="checkbox" id="s-follow"> Follow the printer: a filament loaded on the printer goes to its slicer slot automatically</label>
        <div style="color:var(--mu); margin-top:8px">Tool N is filament slot N in the Prepare tab. Printer → Slicer picks the matching filament preset for each selected slot. Slicer → Printer records each selected slot's filament on the tool in Prusa Connect (a label only; nothing is loaded).</div>
      </div>
    </div>
    <div class="box" id="cat-box"><h4><b id="cat-title">Find a filament</b><span><button id="b-cat-close" style="display:none">Done</button></span></h4><div class="pad">
      <div class="cat-bar"><input type="text" id="cat-q" placeholder="Brand, name or colour, e.g. eSUN PLA+ yellow">
        <button id="b-cat" class="primary">Search</button></div>
      <div class="cat-bar cat-filters">
        <select id="cat-type" title="Material type, as the printer knows it"><option value="">All materials</option><option>PLA</option><option>PETG</option><option>ASA</option><option>ABS</option><option>PC</option><option>PA</option><option value="FLEX">FLEX (TPU)</option><option>PVB</option><option>HIPS</option><option>PP</option><option>PVA</option><option>BVOH</option></select>
        <select id="cat-brand" title="Manufacturer"><option value="">All brands</option></select>
        <select id="cat-color" title="Colour"><option value="">All colours</option><option value="white">● White</option><option value="black">● Black</option><option value="grey">● Grey</option><option value="silver">● Silver</option><option value="gold">● Gold</option><option value="red">● Red</option><option value="orange">● Orange</option><option value="yellow">● Yellow</option><option value="green">● Green</option><option value="blue">● Blue</option><option value="purple">● Purple</option><option value="pink">● Pink</option><option value="brown">● Brown</option><option value="beige">● Beige</option><option value="natural">○ Natural</option><option value="multicolor">◑ Multicolour</option><option value="unknown">? Unknown</option></select>
        <select id="cat-finish" title="Finish"><option value="">All finishes</option><option value="none">Plain (no finish)</option><option value="transparent">Transparent</option><option value="translucent">Translucent</option><option value="silk">Silk</option><option value="matte">Matte</option><option value="glitter">Glitter</option><option value="metallic">Metallic</option><option value="glow">Glow in the dark</option><option value="marble">Marble</option><option value="wood">Wood</option><option value="neon">Neon</option><option value="pastel">Pastel</option><option value="carbon">Carbon look</option></select></div>
      <div id="cat-fit-row" style="display:none; margin-top:8px; gap:18px; align-items:center">
        <label id="cat-fit-label"><input type="checkbox" id="cat-fit" checked> Compatible with nozzle</label>
        <label id="cat-same-label"><input type="checkbox" id="cat-same"> <span id="cat-same-text">Same material as loaded</span></label>
        <small id="cat-hidden" style="color:var(--mu)"></small></div>
      <div id="cat-notice"></div>
      <div id="cat-list"></div>
    </div></div>
  </section>

  <section class="page" id="p-history">
    <div class="col" style="flex: 1.4">
      <div class="box">
        <h4>Print history <small id="h-stats"></small></h4>
        <table><thead><tr><th>Result</th><th>File</th><th>Sent</th><th>Time</th></tr></thead><tbody id="history"></tbody></table>
        <div class="pad" id="h-empty" style="color:var(--mu)">No prints yet. Prints sent from the slicer and prints started on the printer appear here.</div>
      </div>
    </div>
    <div class="col" style="flex: 1">
      <div class="box" id="h-detail" style="display:none">
        <h4 id="hd-title">-</h4>
        <div class="pad kv" id="hd-kv"></div>
        <div class="pad" id="hd-shots" style="display:flex; gap:8px; flex-wrap:wrap; padding-top:0"></div>
        <div class="pad" style="padding-top:0"><div class="btns" style="margin-top:0">
          <button id="hd-reprint" class="primary">Print again</button><button id="hd-open" title="Open the project's folder">Show project</button><button id="hd-delete" class="danger">Remove</button></div></div>
      </div>
    </div>
  </section>

  <section class="page" id="p-settings" style="flex-direction: column">
    <div class="box"><h4>Prusa Connect <span><button id="b-wizard" class="primary">Setup wizard</button></span></h4><div class="pad">
      <div class="kv"><span>Account</span><span id="login">-</span><span>Printer</span>
        <span><select id="printers" style="max-width: 360px"><option value="">-</option></select></span></div>
      <div class="btns"><button id="b-login" class="primary">Log in</button><button id="b-logout">Log out</button>
        <button id="b-printers">List printers</button><button id="b-fill">Fill settings from Connect</button></div>
      <div id="login-code">
        <label>Paste the address from the login redirect (prusaslicer://login?code=...)</label>
        <input type="text" id="code" placeholder="prusaslicer://login?code=...">
        <div class="btns"><button id="b-code" class="primary">Finish login</button></div>
      </div>
    </div></div>
    <div class="box"><h4>Nozzles <small id="nz-preset"></small></h4>
      <table><thead><tr><th><input type="checkbox" id="nz-all" title="Select all"></th><th>Tool</th><th>Printer</th><th>Printer preset</th><th></th></tr></thead><tbody id="nozzles"></tbody></table>
      <div class="pad">
        <div class="btns" style="margin-top:0"><button id="b-nz-preset">Printer → preset</button><button id="b-nz-printer">Preset → printer</button></div>
        <div style="color:var(--mu); margin-top:8px">Nozzle diameter and hardened nozzle per tool. Printer → preset edits the selected printer preset (save it in the slicer to keep it). Preset → printer changes the tool settings on the printer through Prusa Connect. High flow has no setting in Orca's Prusa presets and is only shown.</div>
      </div>
    </div>
    <div class="box"><h4>Notifications <span><button id="b-test-notify">Test</button></span></h4><div class="pad" id="notify" style="display:flex; gap: 6px 18px; flex-wrap: wrap"></div></div>
    <div class="box"><h4>Connection</h4><div class="pad">
      <div class="grid2">
        <div><label>PrusaLink host</label><input type="text" id="s-host">
          <label>PrusaLink password / API key <span id="s-pw-set"></span></label><input type="password" id="s-pw" placeholder="unchanged"></div>
        <div><label>Printer UUID (Connect)</label><input type="text" id="s-uuid">
          <label>Camera RTSP URL (optional)</label><input type="text" id="s-cam" placeholder="rtsp://camera-ip/live"></div>
      </div>
      <div class="btns"><button id="b-save" class="primary">Save settings</button><button id="b-refresh">Refresh now</button></div>
    </div></div>
    <div class="box"><h4>Printer</h4><div class="pad kv">
      <span>Model</span><span id="model">-</span><span>Firmware</span><span id="fw">-</span>
      <span>Address</span><span id="ip">-</span><span>Data source</span><span id="src">-</span>
      <span>Last error</span><span id="err">-</span>
    </div></div>
    <div class="box"><h4>Plugin</h4><div class="pad kv">
      <span>Version</span><span id="ab-version">-</span><span>Installed as</span><span id="ab-kind">-</span>
      <span>Location</span><span id="ab-location" style="word-break: break-all">-</span>
    </div></div>
  </section>
</main>
<div id="busy"><div class="track"><i></i></div><span class="label" id="busy-label"></span></div>
<div id="toast"></div>
<div id="pick" role="dialog" aria-modal="true" aria-labelledby="cat-title"><div class="wbox">
  <div id="pick-slot"></div>
  <div class="wnav btns" style="justify-content:flex-end"><button id="pick-cancel">Cancel</button><button class="primary" id="pick-ok" disabled>Accept</button></div>
</div></div>
<div id="mc" role="dialog" aria-modal="true" aria-labelledby="mc-title"><div class="wbox">
  <h3 id="mc-title">Another material type</h3>
  <div id="mc-text"></div>
  <button class="opt primary" id="mc-swap"><b id="mc-swap-t"></b><small id="mc-swap-s"></small></button>
  <button class="opt" id="mc-orca"><b id="mc-orca-t"></b><small id="mc-orca-s"></small></button>
  <button class="opt" id="mc-cancel"><b>Cancel</b><small>Nothing changes.</small></button>
</div></div>
<div id="wiz" role="dialog" aria-modal="true" aria-labelledby="wiz-title"><div class="wbox">
  <h3 id="wiz-title">Set up your Prusa printer</h3>
  <ol class="wsteps"><li data-s="login">Log in</li><li data-s="printer">Printer</li><li data-s="review">Settings</li><li data-s="test">Test</li></ol>
  <div class="wpane" data-s="login">
    <p>The easiest way: log in to Prusa Connect once, and the plugin reads your printer's network address and PrusaLink key from it.</p>
    <ol class="how"><li>Press <b>Open login page</b> and log in to your Prusa account in the browser.</li>
      <li>At the end the browser asks to open PrusaSlicer. Cancel that, then copy the address from the address bar
        (it starts with <code>prusaslicer://login?code=</code>).</li>
      <li>Paste it below and press <b>Continue</b>.</li></ol>
    <div class="btns"><button id="w-open" class="primary">Open login page</button></div>
    <label for="w-code">Login address</label><input type="text" id="w-code" placeholder="prusaslicer://login?code=...">
    <p class="alt">No Prusa Connect account? <a href="#" id="w-manual">Set up PrusaLink by hand</a>.</p>
  </div>
  <div class="wpane" data-s="printer">
    <p>Choose the printer to use with OrcaSlicer.</p>
    <div id="w-printers" class="wlist"></div>
  </div>
  <div class="wpane" data-s="review">
    <p id="w-found-h">Found in Prusa Connect:</p><ul id="w-found" class="wfound"></ul>
    <div id="w-missing"></div><p id="w-notes" class="wnote"></p>
    <div id="w-manual-fields">
      <label for="w-host">Printer IP address</label><input type="text" id="w-host" placeholder="for example 192.168.1.50">
      <label for="w-pw">PrusaLink password or API key</label><input type="password" id="w-pw">
      <ol class="how"><li>On the printer, open <b>Settings &gt; Network</b> and note the <b>IP address</b>.</li>
        <li>Open <b>Settings &gt; Network &gt; PrusaLink</b>. Make sure PrusaLink is on and note the <b>password</b>
          shown there (the username is always <b>maker</b>).</li></ol>
    </div>
  </div>
  <div class="wpane" data-s="test"><p id="w-result">Testing…</p></div>
  <div class="btns wnav"><button id="w-cancel">Close</button><span style="flex:1"></span>
    <button id="w-back">Back</button><button id="w-next" class="primary">Continue</button></div>
</div></div>

<script>
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var post = function (m) { orca.postMessage(m); };
  function text(id, v) { $(id).textContent = (v === undefined || v === null || v === '') ? '-' : String(v); }
  function show(id, on) { $(id).style.display = on ? '' : 'none'; }
  function deg(v, t) { return Math.round(v) + (t ? ' / ' + Math.round(t) : '') + ' °C'; }
  function hm(s) { s = s || 0; var h = Math.floor(s / 3600), m = Math.round(s % 3600 / 60); return h ? h + 'h ' + m + 'm' : m + 'm'; }

  document.querySelectorAll('nav .tab').forEach(function (b) {
    b.onclick = function () {
      document.querySelectorAll('nav .tab').forEach(function (x) { x.classList.toggle('on', x === b); });
      document.querySelectorAll('.page').forEach(function (p) { p.classList.toggle('on', p.id === 'p-' + b.dataset.page); });
      if (b.dataset.page === 'files') post({ command: 'list_files' });
      if (b.dataset.page === 'history') post({ command: 'history' });
      if (b.dataset.page === 'filament' && !$('cat-list').childNodes.length) catSearch();
    };
  });

  function spool(t) {
    var el = document.createElement('div');
    el.className = 'spool' + (t.material ? '' : ' none');
    if (t.material) el.style.background = t.color || '#9e9e9e';
    return el;
  }
  function toolCard(t, assign) {
    var el = document.createElement('div'); el.className = 'tool' + (t.is_active ? ' on' : '');
    var h = document.createElement('div'); h.className = 't'; h.textContent = t.label || ('T' + t.tool_number); el.appendChild(h);
    el.appendChild(spool(t));
    var txt = document.createElement('div'); txt.className = 'txt';
    var m = document.createElement('small'); m.textContent = t.material || 'empty'; txt.appendChild(m);
    if (t.name) { var n = document.createElement('small'); n.textContent = t.name; txt.appendChild(n); }
    el.appendChild(txt);
    var z = document.createElement('div'); z.className = 'temp'; z.textContent = deg(t.temperature, t.target) + ' · ' + t.nozzle_diameter + ' mm'; el.appendChild(z);
    if (assign) {
      if (t.swap) {
        var sw = document.createElement('small'); sw.className = 'swap';
        sw.textContent = 'Load ' + t.swap.material + ' on the printer: ' + t.swap.title;
        el.appendChild(sw);
        var cx = document.createElement('button'); cx.textContent = 'Cancel change'; cx.style.marginTop = '6px';
        cx.onclick = function () { post({ command: 'cancel_swap', tool: t.tool_number }); };
        el.appendChild(cx);
      }
      if (t.preset) { var pr = document.createElement('small'); pr.className = 'preset'; pr.title = 'Slicer preset'; pr.textContent = t.preset; el.appendChild(pr); }
      var pick = document.createElement('button'); pick.textContent = 'Select filament'; pick.style.marginTop = '6px';
      if (catTool === t.tool_number) pick.className = 'primary';
      pick.onclick = function () { catFor(t.tool_number); };
      el.appendChild(pick);
    } else if (t.material !== undefined) {
      el.title = 'Choose the filament for ' + (t.label || 'T' + t.tool_number);
      el.onclick = function () { pickOpen(t.tool_number); };
    }
    return el;
  }

  var thumbFor = '', toolsKey = '';
  function render(d) {
    $('conn').textContent = d.connected ? 'online' : 'offline';
    $('conn').className = 'pill ' + (d.connected ? 'ok' : 'bad');
    text('phase', d.phase); text('title', d.printer_name || d.name || 'Prusa printer');
    text('model', d.model); text('fw', d.firmware); text('ip', d.ip); text('src', d.source); text('err', d.error);
    text('foot', d.source ? 'Data: ' + d.source : '');
    text('st-state', d.state ? d.state.charAt(0) + d.state.slice(1).toLowerCase() : '');
    text('st-model', d.model); text('st-fw', d.firmware); text('st-ip', d.ip);
    text('st-time', d.job ? hm(d.job.printing) : '');
    text('t-noz', d.connected ? deg(d.nozzle_temp, d.nozzle_target) : '');
    text('t-bed', d.connected ? deg(d.bed_temp, d.bed_target) : '');
    text('t-z', d.z !== undefined && d.z !== null ? d.z.toFixed(1) + ' mm' : '');
    text('t-speed', d.speed ? d.speed + '%' : '');
    text('t-flow', d.flow ? d.flow + '%' : '');
    var act = (d.tools || []).filter(function (t) { return t.is_active; })[0];
    text('t-tool', d.connected ? (act ? act.label : 'none') : '');
    text('t-fan', d.connected ? (d.fan_print ? d.fan_print + ' rpm' : 'off') : '');
    text('t-hfan', d.connected ? (d.fan_hotend ? d.fan_hotend + ' rpm' : 'off') : '');
    var j = d.job;
    text('job-name', j ? j.name : 'No job');
    $('job-bar').style.width = (j ? d.progress : 0) + '%';
    text('job-pct', j ? Math.round(d.progress) : '');
    text('job-layer', j && j.layers ? 'Layer: ' + j.layer + '/' + j.layers : 'Layer: -');
    text('job-left', j ? '-' + hm(j.left) : '');
    show('b-pause', j && d.state === 'PRINTING'); show('b-resume', j && d.state === 'PAUSED'); show('b-stop', !!j);
    if (j && j.file && j.file !== thumbFor) { thumbFor = j.file; post({ command: 'thumbnail', file: j.file }); }
    if (!j) { thumbFor = ''; $('thumb').style.backgroundImage = ''; $('thumb').classList.remove('has'); }
    // Rebuilt only on change, so an open filament list isn't closed by the 3 s poll.
    var key = JSON.stringify([d.tools, d.logged_in]);
    if (key !== toolsKey) {
      toolsKey = key;
      var box = $('tools'), box2 = $('tools-assign'); box.textContent = ''; box2.textContent = '';
      (d.tools || []).forEach(function (t) { box.appendChild(toolCard(t, false)); box2.appendChild(toolCard(t, d.logged_in)); });
    }
    applyAllowed(d);
    toolCount = (d.tools || []).length;
    renderReady(d.ready);
    renderTasks(d.tasks);
    var cw = $('cloud-warn');
    cw.style.display = d.cloud_error ? 'block' : 'none';
    cw.textContent = d.cloud_error ? 'Prusa Connect is not answering (' + d.cloud_error.replace(/^Connect: /, '') + '). Status comes from PrusaLink; tool data and controls may be out of date.' : '';
    banner('identity-error', d.identity_error);
    banner('preset-notice', d.preset_notice);
    setArt(d.family);
    renderExtras(d.extras);
    renderNozzles(d.nozzles);
    filaments.render(d.filaments);
    text('login', d.logged_in ? 'logged in' : 'not logged in');
    show('b-login', !d.logged_in); show('b-logout', d.logged_in); show('login-code', !d.logged_in);
  }
  var wizOffered = false;
  function renderSettings(s) {
    // First run: nothing to talk to yet, so start with the wizard.
    if (!wizOffered) { wizOffered = true; if (!s.prusalink.host && !s.connect.printer_uuid) wizOpen(); }
    if (document.activeElement !== $('s-host')) $('s-host').value = s.prusalink.host || '';
    if (document.activeElement !== $('s-uuid')) $('s-uuid').value = s.connect.printer_uuid || '';
    if (document.activeElement !== $('s-cam')) $('s-cam').value = s.camera.rtsp_url || '';
    $('s-pw-set').textContent = (s.prusalink.password || s.prusalink.api_key) ? '(set)' : '(not set)';
    renderNotify(s.notify);
    $('s-follow').checked = !!(s.filament && s.filament.follow_printer);
    var p = $('printers');
    if (s.connect.printer_uuid && p.options.length <= 1 && p.value !== s.connect.printer_uuid) {
      p.textContent = '';
      var o = document.createElement('option'); o.value = s.connect.printer_uuid;
      o.textContent = (s.printer && s.printer.name) || s.connect.printer_uuid; p.appendChild(o);
    }
  }
  var selected = '', thumbs = {}, wanted = [], busy = false, busyTimer = null;
  function nextThumb() {
    clearTimeout(busyTimer);
    var n = wanted.shift(); busy = !!n;
    if (n) { post({ command: 'thumbnail', file: n }); busyTimer = setTimeout(nextThumb, 20000); }
  }
  // Thumbnails come one at a time from the printer: only fetch rows scrolled into view.
  var seen = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      seen.unobserve(e.target);
      var f = e.target.dataset.file;
      if (thumbs[f] === undefined && wanted.indexOf(f) < 0) wanted.push(f);
    });
    if (!busy) nextThumb();
  });
  function renderFiles(list) {
    var tb = $('files'); tb.textContent = ''; wanted = []; busy = false; seen.disconnect();
    list.forEach(function (f) {
      var tr = document.createElement('tr'); if (f.name === selected) tr.className = 'sel';
      var th = document.createElement('td'); th.className = 'num'; var im = document.createElement('div'); im.className = 'fthumb';
      if (thumbs[f.name]) im.style.backgroundImage = 'url(' + thumbs[f.name] + ')';
      else if (thumbs[f.name] === undefined) seen.observe(im);
      im.dataset.file = f.name; th.appendChild(im); tr.appendChild(th);
      var td = document.createElement('td'); td.textContent = f.display_name || f.name; tr.appendChild(td);
      var tm = document.createElement('td'); tm.className = 'num'; tm.textContent = f.time ? new Date(f.time * 1000).toLocaleString() : ''; tr.appendChild(tm);
      tr.onclick = function () { selected = f.name; renderFiles(list); };
      tb.appendChild(tr);
    });
    if (!list.length) { var tr = document.createElement('tr'); var td = document.createElement('td'); td.textContent = 'No print files'; tr.appendChild(td); tb.appendChild(tr); }
  }

  orca.onMessage(function (m) {
    if (!m) return;
    if (m.type === 'telemetry') render(m.data);
    if (m.type === 'settings') renderSettings(m.data);
    if (m.type === 'catalog') renderCatalog(m);
    if (m.type === 'material_change') materialChange(m);
    if (m.type === 'open_finder' && !picking) pickOpen(m.tool);
    if (m.type === 'about') { $('ab-version').textContent = m.data.version; $('ab-kind').textContent = m.data.kind; $('ab-location').textContent = m.data.location; }
    if (m.type === 'wizard') onWizard(m);
    if (m.type === 'message') { $('msg').textContent = m.text; toast(m.text); if ($('wiz').classList.contains('on')) $('w-next').disabled = false; }
    if (m.type === 'history') renderHistory(m.data);
    if (m.type === 'tasks') { renderTasks(m.data); if (m.finished && m.finished.state === 'timeout') toast(m.finished.label + ': ' + m.finished.error + '. It may still happen; check the printer.'); }
    if (m.type === 'history_shot') { var im = document.querySelector('.shot[data-name="' + m.name + '"]'); if (im) im.src = m.data; }
    if (m.type === 'files') renderFiles(m.data);
    if (m.type === 'confirm_print') {
      // The plugin found problems with this file and the printer as it is now.
      if (m.blocked) alert(m.text);
      else if (confirm(m.text)) post({ command: 'print_file', name: m.name, confirmed: true });
    }
    if (m.type === 'thumbnail') {
      thumbs[m.file] = m.data;
      if (!m.data) { nextThumb(); return; }
      if (m.file === thumbFor) { $('thumb').style.backgroundImage = 'url(' + m.data + ')'; $('thumb').classList.add('has'); }
      document.querySelectorAll('.fthumb').forEach(function (e) { if (e.dataset.file === m.file) e.style.backgroundImage = 'url(' + m.data + ')'; });
      nextThumb();
    }
    if (m.type === 'snapshot') {
      if (m.data) {
        $('cam').src = m.data; show('cam-empty', false);
        $('cam-tag').textContent = m.changed ? 'Picture from ' + m.changed : 'Snapshot'; show('cam-tag', true);
      }
      $('cam-hint').textContent = m.hint || ''; $('cam-hint').style.display = m.hint ? 'block' : 'none';
    }
    if (m.type === 'printers') {
      var s = $('printers'); s.textContent = '';
      var none = document.createElement('option'); none.value = ''; none.textContent = m.data.length ? 'Choose a printer…' : 'No printers found'; s.appendChild(none);
      m.data.forEach(function (p) { var o = document.createElement('option'); o.value = p.uuid; o.textContent = p.name + ' (' + p.model + ')'; s.appendChild(o); });
    }
  });

  var allowed = {}, step = 1, motionOn = false;
  function can(cmd) { return !!allowed[cmd]; }
  function applyMotion() {
    document.querySelectorAll('#jog [data-move]').forEach(function (b) { b.disabled = !motionOn || !can(b.dataset.move === 'z' ? 'MOVE_Z' : 'MOVE'); });
    $('b-home').disabled = !motionOn || !can('HOME'); $('b-motors').disabled = !motionOn || !can('DISABLE_STEPPERS');
    $('b-motion').textContent = motionOn ? 'Disable movement' : 'Enable movement';
    $('b-motion').disabled = !motionOn && !(can('MOVE') || can('MOVE_Z') || can('HOME'));
  }
  function banner(id, textValue) {
    var el = $(id); el.style.display = textValue ? 'block' : 'none'; el.textContent = textValue || '';
  }

  // Setup wizard: log in to Connect, pick the printer, review what Connect knows, test PrusaLink.
  var wiz = { step: 'login', manual: false, proposal: null, busy: false };
  var WSTEPS = ['login', 'printer', 'review', 'test'];
  function wizShow(step) {
    wiz.step = step;
    var i = WSTEPS.indexOf(step);
    document.querySelectorAll('#wiz .wsteps li').forEach(function (li, n) { li.classList.toggle('on', n === i); li.classList.toggle('done', n < i); });
    document.querySelectorAll('#wiz .wpane').forEach(function (p) { p.classList.toggle('on', p.dataset.s === step); });
    show('w-manual-fields', step === 'review' && (wiz.manual || !(wiz.proposal && wiz.proposal.patch.prusalink.api_key && wiz.proposal.patch.prusalink.host)));
    show('w-back', step !== 'login' && step !== 'test');
    show('w-next', step !== 'printer');
    $('w-next').textContent = step === 'review' ? 'Save and test' : step === 'test' ? 'Done' : 'Continue';
    $('w-next').disabled = false;
  }
  function wizOpen() { wiz.manual = false; wiz.proposal = null; $('wiz').classList.add('on'); post({ command: 'wizard_state' }); wizShow('login'); }
  function wizClose() { $('wiz').classList.remove('on'); }
  function wizManual() {
    wiz.manual = true; wiz.proposal = { patch: { prusalink: {}, connect: {}, camera: {}, printer: {} }, found: [], missing: [], notes: [] };
    $('w-found').textContent = ''; $('w-missing').textContent = ''; $('w-notes').textContent = ''; $('w-host').value = '';
    show('w-found-h', false); wizShow('review');
  }
  function onWizard(m) {
    if (m.step === 'state') { if (m.logged_in && wiz.step === 'login') { wizShow('printer'); post({ command: 'wizard_printers' }); } }
    else if (m.step === 'logged_in') { wizShow('printer'); post({ command: 'wizard_printers' }); }
    else if (m.step === 'login_failed') { $('w-next').disabled = false; toast('Login failed: ' + m.text); }
    else if (m.step === 'printers') {
      var box = $('w-printers'); box.textContent = '';
      if (!m.printers.length) { box.textContent = 'No printers in this Prusa account. Add the printer in Prusa Connect first, or set it up by hand.'; }
      m.printers.forEach(function (p) {
        var b = document.createElement('button'); b.textContent = p.name;
        var s = document.createElement('small'); s.textContent = p.model; b.appendChild(s);
        b.onclick = function () { post({ command: 'wizard_read', uuid: p.uuid }); };
        box.appendChild(b);
      });
    } else if (m.step === 'proposal') {
      wiz.proposal = m;
      var ul = $('w-found'); ul.textContent = '';
      m.found.forEach(function (f) { var li = document.createElement('li'); li.textContent = f; ul.appendChild(li); });
      var miss = $('w-missing'); miss.textContent = '';
      m.missing.forEach(function (f) { var p = document.createElement('p'); p.textContent = f; miss.appendChild(p); });
      $('w-notes').textContent = (m.notes || []).join(' '); show('w-found-h', true);
      $('w-host').value = m.patch.prusalink.host || '';
      wizShow('review');
    } else if (m.step === 'tested') {
      var r = $('w-result'); r.textContent = m.text; r.className = m.ok ? 'ok' : 'bad';
      if (!m.ok) { show('w-back', true); }
    }
  }
  $('b-wizard').onclick = wizOpen;
  $('w-cancel').onclick = wizClose;
  $('w-manual').onclick = function (e) { e.preventDefault(); wizManual(); };
  $('w-open').onclick = function () { post({ command: 'login_start' }); };
  $('w-back').onclick = function () {
    if (wiz.step === 'test') { wizShow('review'); return; }
    wizShow(wiz.manual ? 'login' : WSTEPS[Math.max(0, WSTEPS.indexOf(wiz.step) - 1)]);
    if (wiz.step === 'printer') post({ command: 'wizard_printers' });
  };
  $('w-next').onclick = function () {
    if (wiz.step === 'login') {
      if (!$('w-code').value.trim()) { toast('Paste the login address first.'); return; }
      $('w-next').disabled = true;
      post({ command: 'login_finish', code: $('w-code').value.trim() }); $('w-code').value = '';
    } else if (wiz.step === 'review') {
      var patch = JSON.parse(JSON.stringify(wiz.proposal.patch));
      var host = $('w-host').value.trim();
      if ($('w-manual-fields').style.display !== 'none') {
        if (!host) { toast('Enter the printer\'s IP address.'); return; }
        patch.prusalink.host = host;
        if (!$('w-pw').value && !patch.prusalink.api_key) { toast('Enter the PrusaLink password.'); return; }
      }
      var pw = $('w-pw').value; $('w-pw').value = '';
      $('w-result').textContent = 'Testing the connection to the printer\u2026'; $('w-result').className = '';
      wizShow('test');
      post({ command: 'wizard_apply', patch: patch, password: pw });
    } else if (wiz.step === 'test') { wizClose(); }
  };
  var ready = null;
  function renderReady(r) {
    ready = r || null;
    $('ready').style.display = ready ? 'block' : 'none';
    if (!ready) return;
    $('b-ready').textContent = ready.label;
    $('ready-note').textContent = ready.name === 'SET_PRINTER_READY' ? 'Bed clear? Let Prusa Connect start the next queued print.' : 'Ready: Prusa Connect may start the next queued print.';
  }
  $('b-ready').onclick = function () {
    if (!ready) return;
    var q = ready.name === 'SET_PRINTER_READY'
      ? 'Set the printer ready?\n\nOnly do this when the bed is clear: Prusa Connect may then start the next print in its queue.'
      : 'Cancel ready?\n\nPrusa Connect will no longer start queued prints until the printer is set ready again.';
    if (confirm(q)) post({ command: 'control', name: ready.name, kwargs: {} });
  };
  function applyAllowed(d) {
    allowed = d.allowed || {};
    document.querySelectorAll('.temps .set').forEach(function (el) { el.classList.toggle('off', !can(el.dataset.cmd)); });
    applyMotion();
  }
  // One editor under the tiles: a slider and a number kept in step, quick values, Set.
  var setterFor = null;
  function closeSetter() { if (setterFor) setterFor.classList.remove('editing'); setterFor = null; $('setter').classList.remove('on'); }
  function openSetter(el) {
    closeSetter(); setterFor = el; el.classList.add('editing');
    var unit = /TEMPERATURE/.test(el.dataset.cmd) ? '°C' : '%';
    var r = $('setter-range'), n = $('setter-num');
    [r, n].forEach(function (x) { x.min = el.dataset.min; x.max = el.dataset.max; x.step = el.dataset.step; });
    var now = parseInt((el.querySelector('b').textContent.match(/(\d+)\s*(?:°C|%)?\s*$/) || [])[1], 10);
    var target = parseInt((el.querySelector('b').textContent.match(/\/\s*(\d+)/) || [])[1], 10);
    var v = !isNaN(target) ? target : !isNaN(now) && unit === '%' ? now : parseInt(el.dataset.presets.split(',')[1], 10);
    r.value = n.value = v;
    text('setter-label', el.querySelector('small').textContent); text('setter-unit', unit);
    var p = $('setter-presets'); p.textContent = '';
    el.dataset.presets.split(',').forEach(function (x) {
      var b = document.createElement('button'); b.textContent = x === '0' && unit === '°C' ? 'Off' : x + unit;
      b.onclick = function () { r.value = n.value = x; }; p.appendChild(b);
    });
    $('setter').classList.add('on'); n.focus(); n.select();
  }
  function sendSetter() {
    var el = setterFor; if (!el) return;
    var v = parseInt($('setter-num').value, 10), min = parseInt(el.dataset.min, 10), max = parseInt(el.dataset.max, 10);
    if (isNaN(v) || v < min || v > max) { toast('Enter ' + min + '–' + max + '.'); return; }
    var kw = {}; kw[el.dataset.arg] = v;
    post({ command: 'control', name: el.dataset.cmd, kwargs: kw });
    closeSetter();
  }
  $('setter-range').oninput = function () { $('setter-num').value = this.value; };
  $('setter-num').oninput = function () { $('setter-range').value = this.value; };
  $('setter-num').onkeydown = function (e) { if (e.key === 'Enter') sendSetter(); if (e.key === 'Escape') closeSetter(); };
  $('setter-set').onclick = sendSetter;
  $('setter-close').onclick = closeSetter;
  document.querySelectorAll('.temps .set').forEach(function (el) {
    el.onclick = function () { if (el.classList.contains('off')) return; if (setterFor === el) closeSetter(); else openSetter(el); };
  });
  document.querySelectorAll('#steps button').forEach(function (b) {
    b.onclick = function () { document.querySelectorAll('#steps button').forEach(function (x) { x.classList.toggle('on', x === b); }); step = parseFloat(b.textContent); };
  });
  document.querySelectorAll('#jog [data-move]').forEach(function (b) {
    b.onclick = function () {
      var d = step * parseInt(b.dataset.dir, 10);
      if (b.dataset.move === 'z') post({ command: 'control', name: 'MOVE_Z', kwargs: { feedrate: 600, distance: d } });
      else { var kw = { feedrate: 3000 }; kw[b.dataset.move] = d; post({ command: 'control', name: 'MOVE', kwargs: kw }); }
    };
  });
  $('b-motion').onclick = function () {
    if (!motionOn && !confirm('Enable manual movement?\n\nThe camera picture is a snapshot that can be several seconds old, so it may not show the printer\'s current state. Make sure nothing is in the way of the tool heads and the bed before moving.')) return;
    motionOn = !motionOn; applyMotion();
  };
  $('b-home').onclick = function () { post({ command: 'control', name: 'HOME', kwargs: { axis: 'XYZ' } }); };
  $('b-motors').onclick = function () { post({ command: 'control', name: 'DISABLE_STEPPERS', kwargs: {} }); };

  // A sync table: one checkbox per tool. Differing tools start checked; the user's choice survives polls.
  function syncTable(body, all, buttons, cells) {
    var picked = {}, key = '';
    function update() {
      var boxes = body.querySelectorAll('input'), n = 0;
      boxes.forEach(function (b) { if (b.checked) n++; });
      all.checked = n && n === boxes.length; all.indeterminate = n > 0 && n < boxes.length;
      buttons.forEach(function (b) { $(b).disabled = !n; });
    }
    all.onchange = function () { body.querySelectorAll('input').forEach(function (b) { b.checked = all.checked; picked[b.value] = b.checked; }); update(); };
    return {
      render: function (rows) {
        var k = JSON.stringify(rows || null);
        if (k === key) return; key = k;
        body.textContent = '';
        (rows || []).forEach(function (r) {
          var c = cells(r), tr = document.createElement('tr'), td = document.createElement('td');
          var cb = document.createElement('input'); cb.type = 'checkbox'; cb.value = r.tool_number;
          cb.checked = r.tool_number in picked ? picked[r.tool_number] : c.differs;
          cb.onchange = function () { picked[r.tool_number] = cb.checked; update(); };
          td.appendChild(cb); tr.appendChild(td);
          tr.onclick = function (e) { if (e.target !== cb) { cb.checked = !cb.checked; cb.onchange(); } };
          c.cols.forEach(function (v) { var t = document.createElement('td'); if (v && v.nodeType) t.appendChild(v); else t.textContent = v; tr.appendChild(t); });
          var s = document.createElement('td'), b = document.createElement('span'); b.className = 'res ' + (c.differs ? 'failed' : 'finished'); b.textContent = c.differs ? 'differs' : 'matches'; s.appendChild(b); tr.appendChild(s);
          body.appendChild(tr);
        });
        update();
      },
      selected: function () { return [].slice.call(body.querySelectorAll('input:checked')).map(function (b) { return +b.value; }); }
    };
  }
  function swatch(color, label) {
    var s = document.createElement('span'), i = document.createElement('i');
    i.style.cssText = 'display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:-2px;margin-right:6px;'
      + (color ? 'border:1px solid var(--bd);background:' + color : 'border:1px dashed var(--bd);opacity:.5');
    i.title = color ? color : 'No colour known';
    s.appendChild(i); s.appendChild(document.createTextNode(label)); return s;
  }

  // Filament finder (Filament page): for one tool after its Select filament button, else general.
  var toolCount = 0, catTool = 0;
  var SOURCE_NAMES = { orca: 'Already in the slicer', connect: 'Prusa Connect', ofd: 'Open Filament Database' };
  var SOURCE_ICONS = {
    orca: '<path d="M12 2l9 5v10l-9 5-9-5V7z" fill="none" stroke="#009688" stroke-width="2"/><path d="M3 7l9 5 9-5M12 12v10" fill="none" stroke="#009688" stroke-width="2"/>',
    connect: '<circle cx="12" cy="12" r="10" fill="#fa6831"/><path d="M9 7h4.5a3 3 0 0 1 0 6H9zM9 13v4" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/>',
    ofd: '<ellipse cx="12" cy="5.5" rx="8" ry="3" fill="none" stroke="#5b7fd6" stroke-width="2"/><path d="M4 5.5v13c0 1.7 3.6 3 8 3s8-1.3 8-3v-13M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" fill="none" stroke="#5b7fd6" stroke-width="2"/>'
  };
  function sourceIcons(sources) {
    var box = document.createElement('span'); box.className = 'src';
    box.title = sources.map(function (s) { return SOURCE_NAMES[s] || s; }).join(' + ');
    sources.forEach(function (s) {
      if (!SOURCE_ICONS[s]) return;
      box.insertAdjacentHTML('beforeend', '<svg viewBox="0 0 24 24" width="16" height="16" aria-label="' + SOURCE_NAMES[s] + '">' + SOURCE_ICONS[s] + '</svg>');
    });
    return box;
  }
  function catSearch() {
    post({ command: 'catalog_search', query: $('cat-q').value.trim(), material: $('cat-type').value, tool: catTool,
           brand: $('cat-brand').value, color: $('cat-color').value, finish: $('cat-finish').value, fit: $('cat-fit').checked, same: $('cat-same').checked });
  }
  // Status page: the same finder in a dialog; pick a row, then Accept (or double-click it).
  var picking = false, pickedKey = '';
  function pickSelect(key) {
    pickedKey = key; $('pick-ok').disabled = !key;
    document.querySelectorAll('#cat-list .row').forEach(function (r) { r.classList.toggle('picked', r.dataset.key === key); });
  }
  function pickOpen(tool) {
    picking = true; pickSelect('');
    $('pick-slot').appendChild($('cat-box'));
    $('pick').classList.add('on');
    catFor(tool);
  }
  function pickClose() {
    picking = false; pickSelect('');
    $('p-filament').appendChild($('cat-box'));
    $('pick').classList.remove('on');
    catFor(0);
  }
  function pickAccept() {
    if (!pickedKey) return;
    post({ command: 'catalog_use', key: pickedKey, tool: catTool });
    pickClose();
  }
  $('pick-ok').onclick = pickAccept;
  $('pick-cancel').onclick = pickClose;
  $('pick').addEventListener('keydown', function (e) { if (e.key === 'Escape') pickClose(); });
  function catFor(tool) {
    catTool = tool; toolsKey = '';
    text('cat-title', tool ? 'Select filament for T' + tool : 'Find a filament');
    show('b-cat-close', !!tool && !picking);
    $('cat-fit').checked = true; $('cat-same').checked = false; $('cat-q').value = '';
    $('cat-type').value = ''; $('cat-brand').value = ''; $('cat-color').value = ''; $('cat-finish').value = '';
    catSearch();
    if (!picking) $('cat-box').scrollIntoView({ behavior: 'smooth', block: 'start' });
    $('cat-q').focus();
  }
  $('b-cat-close').onclick = function () { catFor(0); };
  $('b-cat').onclick = catSearch;
  $('cat-fit').onchange = catSearch;
  $('cat-same').onchange = catSearch;
  $('cat-type').onchange = catSearch;
  $('cat-brand').onchange = catSearch;
  $('cat-color').onchange = catSearch;
  $('cat-finish').onchange = catSearch;
  // Colour the swatch dots in the colour menu.
  var DOT = { white: '#f4f4f4', black: '#222', grey: '#8a8a8a', silver: '#c0c4c8', gold: '#d4a017', red: '#d32f2f', orange: '#f57c00',
              yellow: '#fbc02d', green: '#388e3c', blue: '#1976d2', purple: '#7b1fa2', pink: '#ec4f9c', brown: '#795548', beige: '#d9c39a' };
  [].forEach.call($('cat-color').options, function (o) { if (DOT[o.value]) o.style.color = DOT[o.value]; });
  function fillBrands(names) {
    var sel = $('cat-brand'); if (!names || sel.options.length > 1) return;
    names.forEach(function (n) { var o = document.createElement('option'); o.textContent = n; sel.appendChild(o); });
  }
  $('cat-q').onkeydown = function (e) { if (e.key === 'Enter') catSearch(); };
  function renderCatalog(m) {
    if (m.tool !== catTool) return;  // an answer for a tool the user already left
    fillBrands(m.brands);
    var n = $('cat-notice'); n.textContent = m.notice || ''; n.style.display = m.notice ? 'block' : 'none';
    $('cat-fit-row').style.display = m.tool ? 'flex' : 'none';
    $('cat-fit-label').title = m.nozzle || '';
    $('cat-same-label').style.display = m.loaded ? '' : 'none';
    if (m.loaded) {
      text('cat-same-text', 'Same material as loaded (' + m.loaded + ')');
      $('cat-same-label').title = 'T' + m.tool + ' has ' + m.loaded + ' loaded. Loads and prints the same:\n' + m.same_types.join(', ');
    }
    $('cat-hidden').textContent = m.hidden ? m.hidden + ' hidden' : '';
    var list = $('cat-list'); list.textContent = '';
    if (!m.results.length) {
      var e = document.createElement('div'); e.style.color = 'var(--mu)'; e.style.padding = '8px 0';
      e.textContent = m.query ? 'Nothing found for "' + m.query + '". Try fewer words, or the brand and material only.'
        : !m.recent ? 'Nothing matches these filters. Clear one of them.'
        : (m.recent && m.hidden ? 'None of your recent filaments fits this nozzle. Search for one.' : 'No recent filaments yet. Type a brand, name or colour and press Search.');
      list.appendChild(e); return;
    }
    var group = null;
    m.results.forEach(function (r) {
      if (r.group !== group) { group = r.group; var h = document.createElement('div'); h.className = 'brand'; h.textContent = r.group_label || 'Unknown brand'; list.appendChild(h); }
      var row = document.createElement('div'); row.className = 'row';
      var nm = document.createElement('span'); nm.className = 'nm'; nm.appendChild(swatch(r.color, /^(All recent|Recent for )/.test(group) ? r.title : r.name));
      var bits = [r.type];
      if (r.abrasive) bits.push('abrasive');
      if (r.high_flow) bits.push('high flow');
      if (!r.has_data) bits.push('no print data');
      var info = document.createElement('small'); info.textContent = bits.join(' · '); nm.appendChild(info);
      row.appendChild(nm);
      row.appendChild(sourceIcons(r.sources));
      if (picking) {
        row.className = 'row pickable'; row.dataset.key = r.key;
        row.onclick = function () { pickSelect(r.key); };
        row.onmousedown = function (e) { if (e.detail > 1) e.preventDefault(); };
        row.ondblclick = function (e) { e.preventDefault(); window.getSelection().removeAllRanges(); pickSelect(r.key); pickAccept(); };
        list.appendChild(row);
        return;
      }
      if (catTool) row.appendChild(catButton('Use for T' + catTool, r.key, catTool, 'T' + catTool + ' slices with this filament; Prusa Connect records it on the tool', true));
      if (r.source !== 'orca') row.appendChild(catButton(catTool ? 'Add only' : 'Add to slicer', r.key, 0, 'Add to the slicer\'s filament list without using it yet', false));
      list.appendChild(row);
    });
  }
  // The chosen filament is another material type than the tool has loaded: the printer must unload and load.
  function materialChange(m) {
    var t = 'T' + m.tool;
    $('mc-text').textContent = t + ' has ' + m.loaded_name + ' (' + m.loaded + ') loaded. You chose ' + m.chosen_name + ' (' + m.chosen + '). '
      + 'The printer only accepts another material type after an unload and a load.';
    text('mc-swap-t', 'Change the filament on ' + t + ' now');
    text('mc-swap-s', m.can_swap ? 'The printer unloads ' + m.loaded + ' (the nozzle heats up). Then load ' + m.chosen
      + ' from the printer\'s menu; the plugin records ' + m.chosen_name + ' on the tool once the printer reports ' + m.chosen + '.'
      : m.printing ? 'Not while the printer is printing.' : 'Needs Prusa Connect: log in under Settings.');
    $('mc-swap').disabled = !m.can_swap;
    text('mc-orca-t', 'Only slice with it');
    text('mc-orca-s', 'Sets slicer slot ' + m.tool + ' to ' + m.chosen_name + '. The printer keeps ' + m.loaded + ' and will warn at print start until you load ' + m.chosen + '.');
    function answer(mode) { $('mc').classList.remove('on'); if (mode) post({ command: 'catalog_use', key: m.key, tool: m.tool, mode: mode }); }
    $('mc-swap').onclick = function () { answer('swap'); };
    $('mc-orca').onclick = function () { answer('orca'); };
    $('mc-cancel').onclick = function () { answer(''); };
    $('mc').classList.add('on');
  }
  function catButton(label, key, tool, title, primary) {
    var b = document.createElement('button'); b.textContent = label; b.title = title;
    if (primary) b.className = 'primary';
    b.onclick = function () { post({ command: 'catalog_use', key: key, tool: tool }); };
    return b;
  }

  // Controls locked while a task holds their resource (see prusa_orca/tasks.py).
  var LOCKS = {
    job: ['b-pause', 'b-resume', 'b-stop', 'b-print', 'hd-reprint'],
    'sync-nozzles': ['b-nz-preset', 'b-nz-printer'], 'sync-filaments': ['b-fs-orca', 'b-fs-printer'],
    catalog: ['b-cat'], 'catalog-import': ['#cat-list'],
    files: ['b-files'], 'list-printers': ['b-printers'], login: ['b-code', 'b-login'], fill: ['b-fill'],
    MOVE: ['#jog'], MOVE_Z: ['#jog'], HOME: ['#jog'], DISABLE_STEPPERS: ['b-motors'],
    SET_NOZZLE_TEMPERATURE: ['.set[data-cmd=SET_NOZZLE_TEMPERATURE]'], SET_HEATBED_TEMPERATURE: ['.set[data-cmd=SET_HEATBED_TEMPERATURE]'],
    SET_SPEED: ['.set[data-cmd=SET_SPEED]'], SET_FLOW: ['.set[data-cmd=SET_FLOW]'], 'tool-*': ['#tools-assign']
  };
  function lockEls(sel) {
    return sel.charAt(0) === '#' || sel.charAt(0) === '.' ? [].slice.call(document.querySelectorAll(sel)) : [$(sel)].filter(Boolean);
  }
  var busyStart = 0;
  function renderTasks(tasks) {
    tasks = tasks || [];
    document.querySelectorAll('.waiting').forEach(function (e) { e.classList.remove('waiting'); });
    tasks.forEach(function (t) {
      var sels = LOCKS[t.resource] || (t.resource.indexOf('tool-') === 0 ? LOCKS['tool-*'] : []);
      sels.forEach(function (s) { lockEls(s).forEach(function (e) { e.classList.add('waiting'); }); });
    });
    var bar = $('busy');
    bar.classList.toggle('on', tasks.length > 0);
    document.body.classList.toggle('busy', tasks.length > 0);
    document.querySelectorAll('.waiting').forEach(function (e) { e.title = 'Waiting for the printer to answer'; });
    bar.classList.toggle('slow', tasks.some(function (t) { return t.slow; }));
    if (!tasks.length) return;
    var t = tasks[0], more = tasks.length > 1 ? ' (+' + (tasks.length - 1) + ')' : '';
    $('busy-label').textContent = t.label + (t.slow ? ' — waiting for an answer (' + Math.round(t.elapsed) + ' s)' : '…') + more;
  }

  var artMap = null, artFamily = '';
  function setArt(family) {
    if (!family || family === artFamily || !$('art')) return;
    if (!artMap) { try { artMap = JSON.parse($('art-map').textContent); } catch (e) { artMap = {}; } }
    if (artMap[family]) { $('art').src = artMap[family]; artFamily = family; }
  }

  var extrasKey = '';
  function renderExtras(list) {
    var k = JSON.stringify(list || []);
    if (k === extrasKey) return; extrasKey = k;
    var box = $('extras'); box.textContent = '';
    show('extras', list && list.length);
    (list || []).forEach(function (x) {
      var l = document.createElement('span'); l.textContent = x.label; box.appendChild(l);
      var c = document.createElement('span'); c.style.cssText = 'display:flex; gap:6px; justify-content:flex-end';
      function send(v) { var kw = {}; kw[x.arg] = v; post({ command: 'control', name: x.name, kwargs: kw }); }
      if (x.type === 'boolean') {
        ['On', 'Off'].forEach(function (t) {
          var b = document.createElement('button'); b.textContent = t; b.disabled = !x.enabled;
          b.onclick = function () { send(t === 'On'); }; c.appendChild(b);
        });
      } else {
        var i = document.createElement('input'); i.type = 'number'; i.style.width = '80px'; i.disabled = !x.enabled;
        var b = document.createElement('button'); b.textContent = 'Set'; b.disabled = !x.enabled;
        b.onclick = function () { var v = parseFloat(i.value); if (!isNaN(v)) send(x.type === 'number' ? v : Math.round(v)); };
        c.appendChild(i); c.appendChild(b);
      }
      box.appendChild(c);
    });
  }

  var nozzles = syncTable($('nozzles'), $('nz-all'), ['b-nz-preset', 'b-nz-printer'], function (r) {
    return { differs: r.diameter_differs || r.hardened_differs, cols: [
      'T' + r.tool_number,
      r.printer.diameter + ' mm' + (r.printer.hardened ? ', hardened' : '') + (r.printer.high_flow ? ', high flow' : ''),
      (r.preset.diameter == null ? '-' : r.preset.diameter + ' mm') + (r.preset.type ? ', ' + r.preset.type.replace(/_/g, ' ') : '')] };
  });
  function renderNozzles(n) { text('nz-preset', n ? n.preset : ''); nozzles.render(n && n.rows); }
  $('b-nz-preset').onclick = function () { post({ command: 'sync_nozzles', direction: 'to_preset', tools: nozzles.selected() }); };
  $('b-nz-printer').onclick = function () {
    var t = nozzles.selected();
    if (confirm('Change the nozzle settings stored on the printer for ' + t.map(function (n) { return 'T' + n; }).join(', ') + ' to match the slicer preset?'))
      post({ command: 'sync_nozzles', direction: 'to_printer', tools: t });
  };

  var filaments = syncTable($('fsync'), $('fs-all'), ['b-fs-orca', 'b-fs-printer'], function (r) {
    var label = [r.printer.vendor, r.printer.name || r.printer.material].filter(Boolean).join(' ');
    var p = !r.printer.loaded ? 'empty' : r.printer.color ? swatch(r.printer.color, label) : label + ' (no colour set)';
    var o = r.slot ? swatch(r.slot.color, r.slot.preset) : 'no slot';
    if (r.preset_differs) o.title = 'Matching preset: ' + r.match;
    if (r.type_differs) {
      var w = document.createElement('span'); w.appendChild(o);
      var b = document.createElement('small'); b.style.cssText = 'display:block;color:var(--danger)';
      b.textContent = 'Slices ' + r.slot_type + ', the printer has ' + r.printer.material + ' loaded';
      w.appendChild(b); o = w;
    }
    return { differs: r.preset_differs || r.color_differs || r.type_differs, cols: ['T' + r.tool_number, p, o] };
  });
  $('b-fs-orca').onclick = function () { post({ command: 'sync_filaments', direction: 'to_orca', tools: filaments.selected() }); };
  $('b-fs-printer').onclick = function () {
    var t = filaments.selected();
    if (confirm('Record the slicer filament of ' + t.map(function (n) { return 'T' + n; }).join(', ') + ' on the printer in Prusa Connect?'))
      post({ command: 'sync_filaments', direction: 'to_printer', tools: t });
  };

  var toastTimer = 0;
  function toast(t) {
    if (!t) return;
    var el = $('toast'); el.textContent = t; el.classList.add('on');
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { el.classList.remove('on'); }, 6000);
  }

  var RESULT = { finished: 'Finished', printing: 'Printing', paused: 'Paused', attention: 'Needs attention', stopped: 'Stopped',
                 failed: 'Failed', sending: 'Sending', uploaded: 'Uploaded', send_failed: 'Send failed', not_started: 'Not started',
                 unknown: 'Unknown', replaced: 'Superseded' };
  var history = [], histSel = '';
  function when(s) { return s ? new Date(s * 1000).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' }) : ''; }
  function badge(r) { var b = document.createElement('span'); b.className = 'res ' + r.result; b.textContent = RESULT[r.result] || r.result; return b; }
  function renderHistory(list) {
    history = list || [];
    var body = $('history'); body.textContent = '';
    show('h-empty', !history.length);
    var done = history.filter(function (r) { return r.result === 'finished' || r.result === 'stopped' || r.result === 'failed'; });
    var ok = done.filter(function (r) { return r.result === 'finished'; }).length;
    $('h-stats').textContent = done.length ? ok + ' of ' + done.length + ' finished' : '';
    history.forEach(function (r) {
      var tr = document.createElement('tr'); if (r.id === histSel) tr.className = 'sel';
      var c1 = document.createElement('td'); c1.appendChild(badge(r)); tr.appendChild(c1);
      var c2 = document.createElement('td'); c2.textContent = r.file + (r.plate > 1 ? ' (plate ' + r.plate + ')' : ''); tr.appendChild(c2);
      var c3 = document.createElement('td'); c3.className = 'num'; c3.textContent = when(r.sent || r.started); tr.appendChild(c3);
      var est = (r.meta || {}).estimated_seconds;
      var c4 = document.createElement('td'); c4.className = 'num'; c4.textContent = r.printing_seconds ? hm(r.printing_seconds) : est ? '~' + hm(est) : '–'; tr.appendChild(c4);
      tr.onclick = function () { histSel = r.id; renderHistory(history); };
      body.appendChild(tr);
    });
    renderDetail(history.filter(function (r) { return r.id === histSel; })[0]);
  }
  function renderDetail(r) {
    show('h-detail', !!r);
    if (!r) return;
    $('hd-title').textContent = r.file;
    var kv = $('hd-kv'); kv.textContent = '';
    var meta = r.meta || {}, presets = r.presets || {};
    var rows = [['Result', badge(r)], ['Error', r.error], ['Project', r.project_path || r.project],
      ['Sent', when(r.sent)], ['Started', when(r.started)], ['Ended', when(r.ended)],
      ['Progress', r.layers ? Math.round(r.progress) + '% · layer ' + r.layer + '/' + r.layers : Math.round(r.progress || 0) + '%'],
      ['Print time', r.printing_seconds ? hm(r.printing_seconds) + (meta.estimated_seconds ? ' (estimated ' + hm(meta.estimated_seconds) + ')' : '') : (meta.estimated_seconds ? 'estimated ' + hm(meta.estimated_seconds) : '')],
      ['Filament', (meta.used_tools || []).map(function (i) { return 'T' + (i + 1) + ' ' + ((meta.filament_presets || [])[i] || (meta.filament_types || [])[i] || '') + (meta.filament_used_g && meta.filament_used_g[i] ? ' · ' + meta.filament_used_g[i].toFixed(1) + ' g' : ''); }).join('\n')],
      ['Printer preset', presets.printer], ['Process', presets.process],
      ['Checks', (r.preflight || []).join('\n')], ['Source', r.source === 'printer' ? 'Started on the printer or in Connect' : '']];
    rows.forEach(function (row) {
      if (!row[1]) return;
      var k = document.createElement('span'); k.textContent = row[0]; kv.appendChild(k);
      var v = document.createElement('span'); v.style.whiteSpace = 'pre-line';
      if (row[1].nodeType) v.appendChild(row[1]); else v.textContent = row[1];
      kv.appendChild(v);
    });
    var shots = $('hd-shots'); shots.textContent = '';
    Object.keys(r.snapshots || {}).forEach(function (ev) {
      var w = document.createElement('div'), im = document.createElement('img');
      im.className = 'shot'; im.dataset.name = r.snapshots[ev]; im.alt = '';
      var cap = document.createElement('div'); cap.className = 'shot-cap'; cap.textContent = ev.replace('_', ' ');
      w.appendChild(im); w.appendChild(cap); shots.appendChild(w);
      post({ command: 'history_shot', name: r.snapshots[ev] });
    });
    $('hd-reprint').disabled = !r.file || r.result === 'send_failed';
    $('hd-open').disabled = !r.project_path;
    $('hd-open').title = r.project_path ? r.project_path : 'The project was never saved, so there is no file to show.';
  }
  $('hd-reprint').onclick = function () {
    var r = history.filter(function (x) { return x.id === histSel; })[0];
    if (r && confirm('Print ' + r.file + ' again from the printer\'s storage now?')) post({ command: 'print_file', name: r.file });
  };
  $('b-test-notify').onclick = function () { post({ command: 'test_notify' }); };
  $('s-follow').onchange = function () { post({ command: 'save_settings', patch: { filament: { follow_printer: $('s-follow').checked } }, quiet: true }); };
  $('hd-open').onclick = function () { post({ command: 'history_open', id: histSel }); };
  $('hd-delete').onclick = function () { if (histSel) { post({ command: 'history_remove', id: histSel }); histSel = ''; } };

  var NOTIFY = { started: 'Print started', first_layer: 'First layer done', near_end: '10 minutes left', paused: 'Paused',
                 attention: 'Needs attention', finished: 'Finished', stopped: 'Stopped', failed: 'Failed' };
  function renderNotify(n) {
    var box = $('notify'); box.textContent = '';
    Object.keys(NOTIFY).forEach(function (k) {
      var l = document.createElement('label'); l.style.cssText = 'display:flex; gap:6px; align-items:center; margin:0; color:inherit';
      var cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = !n || n[k] !== false;
      cb.onchange = function () { var p = { notify: {} }; p.notify[k] = cb.checked; post({ command: 'save_settings', patch: p, quiet: true }); };
      l.appendChild(cb); l.appendChild(document.createTextNode(NOTIFY[k])); box.appendChild(l);
    });
  }

  $('b-pause').onclick = function () { post({ command: 'job', action: 'pause' }); };
  $('b-resume').onclick = function () { post({ command: 'job', action: 'resume' }); };
  $('b-stop').onclick = function () { if (confirm('Stop the current print? It cannot be resumed.')) post({ command: 'job', action: 'stop' }); };
  $('b-files').onclick = function () { post({ command: 'list_files' }); };
  $('b-print').onclick = function () {
    if (!selected) return;
    var row = document.querySelector('#files tr.sel td');
    if (confirm('Start printing ' + (row ? row.textContent : selected) + ' now?')) post({ command: 'print_file', name: selected });
  };
  $('b-printers').onclick = function () { post({ command: 'list_printers' }); };
  $('printers').onchange = function () { if ($('printers').value) post({ command: 'choose_printer', uuid: $('printers').value }); };
  $('b-refresh').onclick = function () { post({ command: 'refresh' }); };
  $('b-login').onclick = function () { post({ command: 'login_start' }); };
  $('b-logout').onclick = function () { post({ command: 'logout' }); };
  $('b-fill').onclick = function () { post({ command: 'fill_from_connect' }); };
  $('b-code').onclick = function () { post({ command: 'login_finish', code: $('code').value }); $('code').value = ''; };
  $('b-save').onclick = function () {
    var patch = { prusalink: { host: $('s-host').value.trim() }, connect: { printer_uuid: $('s-uuid').value.trim() }, camera: { rtsp_url: $('s-cam').value.trim() } };
    if ($('s-pw').value) patch.prusalink.password = $('s-pw').value;
    $('s-pw').value = '';
    post({ command: 'save_settings', patch: patch });
  };

  post({ command: 'init' });
  post({ command: 'snapshot' });
  setInterval(function () { post({ command: 'poll' }); }, 3000);
  setInterval(function () { post({ command: 'snapshot' }); }, 10000);
})();
</script>
</body></html>
"""
PAGES_HTML = PAGES_HTML.replace("__PRINTER_SVG__", printer_image_html())
