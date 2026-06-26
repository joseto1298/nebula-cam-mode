# Moonraker component for Nebula Camera NC01
import asyncio
import json
import os
import logging

SCRIPT = os.path.expanduser("~/nebula-cam-mode/nebula_cam_mode.py")


class CameraMode:
    def __init__(self, config):
        self.server = config.get_server()
        self.logger = logging.getLogger(__name__)

        self.server.register_endpoint(
            "/machine/camera_mode/panel", ["GET"], self._handle_panel, wrap_result=False
        )
        self.server.register_endpoint(
            "/machine/camera_mode/status", ["GET"], self._handle_status
        )
        self.server.register_endpoint(
            "/machine/camera_mode/info", ["GET"], self._handle_info
        )
        self.server.register_endpoint(
            "/machine/camera_mode/day", ["POST"], self._handle_day
        )
        self.server.register_endpoint(
            "/machine/camera_mode/night", ["POST"], self._handle_night
        )
        self.server.register_endpoint(
            "/machine/camera_mode/auto", ["POST"], self._handle_auto
        )
        self.server.register_endpoint(
            "/machine/camera_mode/expose", ["POST"], self._handle_expose
        )
        self.server.register_endpoint(
            "/machine/camera_mode/set", ["POST"], self._handle_set
        )
        self.server.register_endpoint(
            "/machine/camera_mode/get", ["GET"], self._handle_get
        )

    async def _run(self, *args):
        cmd = ["sudo", "python3", SCRIPT] + [str(a) for a in args] + ["-j"]
        self.logger.debug("Running: %s", " ".join(cmd))
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=10
            )
            if proc.returncode != 0:
                err = stderr.decode().strip()
                self.logger.error("Script error: %s", err)
                return {"error": err}
            out = stdout.decode().strip()
            if out:
                return json.loads(out)
            return {"status": "ok"}
        except asyncio.TimeoutError:
            self.logger.error("Command timed out: %s", " ".join(cmd))
            return {"error": "command timed out"}
        except json.JSONDecodeError:
            self.logger.error("Invalid JSON from script: %s", out)
            return {"output": out, "error": "invalid JSON"}
        except Exception as e:
            self.logger.error("Unexpected error: %s", e)
            return {"error": str(e)}

    async def _handle_panel(self, web_request):
        status = await self._run("status")
        info = await self._run("info")
        return self._render_panel(status, info)

    async def _handle_status(self, web_request):
        return await self._run("status")

    async def _handle_info(self, web_request):
        return await self._run("info")

    async def _handle_day(self, web_request):
        return await self._run("day")

    async def _handle_night(self, web_request):
        return await self._run("night")

    async def _handle_auto(self, web_request):
        return await self._run("auto")

    async def _handle_expose(self, web_request):
        body = web_request.get_body() or {}
        mode = body.get("mode", "auto")
        val = body.get("value")
        args = ["expose", mode]
        if val is not None:
            args.append(str(val))
        return await self._run(*args)

    async def _handle_set(self, web_request):
        body = web_request.get_body() or {}
        ctrl = body.get("control")
        val = body.get("value")
        if not ctrl or val is None:
            return {"error": "control and value required"}
        return await self._run("set", ctrl, str(val))

    async def _handle_get(self, web_request):
        ctrl = web_request.get_str("control", None)
        if not ctrl:
            return {"error": "control parameter required"}
        return await self._run("get", ctrl)

    def _render_panel(self, status, info):
        ir_mode = status.get("ir_mode", {}).get("name", "Unknown")
        ir_short = status.get("ir_mode", {}).get("short", "unknown")
        firmware = status.get("firmware", info.get("firmware", "Unknown"))

        ctrls = ""
        for k in sorted(status.keys()):
            if k in ("device", "ir_mode", "firmware", "auto_exposure"):
                continue
            v = status[k]
            if isinstance(v, bool) or k in (
                "white_balance_automatic", "focus_automatic_continuous"
            ):
                ctrls += (
                    f"<div class='row'><span class='label'>{k}</span>"
                    f"<span class='value'>{'ON' if v else 'OFF'}</span></div>"
                )
            elif isinstance(v, (int, float)):
                ctrls += (
                    f"<div class='row'><span class='label'>{k}</span>"
                    f"<span class='value'>{v}</span></div>"
                )

        return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CAM MODE</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#1a1a2e;color:#eee;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0;padding:16px}}
.card{{background:#16213e;border-radius:12px;padding:24px;width:100%;max-width:420px;box-shadow:0 8px 32px rgba(0,0,0,.4)}}
h1{{font-size:20px;text-align:center;color:#e94560;margin-bottom:8px}}
.sub{{text-align:center;font-size:12px;color:#666;margin-bottom:20px}}
.mode{{display:flex;gap:10px;margin-bottom:16px}}
.mode button{{flex:1;padding:14px 0;border:none;border-radius:8px;font-size:14px;font-weight:700;cursor:pointer;transition:all .12s;color:#fff;opacity:.5}}
.mode button.active{{opacity:1;transform:scale(1.03);box-shadow:0 4px 16px rgba(0,0,0,.3)}}
.mode button:active{{transform:scale(.95)}}
.btn-day{{background:#4a9eff}}
.btn-day.active{{box-shadow:0 4px 16px rgba(74,158,255,.4)}}
.btn-night{{background:#2c3e50}}
.btn-night.active{{box-shadow:0 4px 16px rgba(44,62,80,.4)}}
.btn-auto{{background:#6c757d}}
.btn-auto.active{{box-shadow:0 4px 16px rgba(108,117,125,.4)}}
.msg{{padding:10px;border-radius:6px;font-size:13px;text-align:center;min-height:36px;background:#0f3460;margin-bottom:14px}}
.msg.ok{{color:#4caf50}}
.msg.err{{color:#e94560}}
.msg.wait{{color:#8892b0}}
.row{{display:flex;justify-content:space-between;padding:6px 0;font-size:13px;border-bottom:1px solid #1e2a4a}}
.row:last-child{{border:none}}
.row .label{{color:#8892b0}}
.row .value{{color:#eee;font-weight:600}}
.controls{{margin-top:12px}}
</style>
</head>
<body>
<div class="card">
<h1>NEBULA CAM</h1>
<p class="sub">Creality NC01 &middot; <span id="fw">{firmware}</span></p>
<div id="msg" class="msg">Pulsa DAY, NIGHT o AUTO</div>
<div class="mode">
<button class="btn-day" onclick="setM('day')">DAY</button>
<button class="btn-night" onclick="setM('night')">NIGHT</button>
<button class="btn-auto" onclick="setM('auto')">AUTO</button>
</div>
<div id="info"><div class='controls'>{ctrls}</div></div>
</div>
<script>
function b(m){{return document.querySelector('.mode .btn-'+m)}}
function a(m){{document.querySelectorAll('.mode button').forEach(function(x){{x.classList.remove('active')}});var x=b(m);if(x)x.classList.add('active')}}
async function setM(m){{
var msg=document.getElementById('msg');
msg.className='msg wait';msg.textContent='Cambiando a '+m.toUpperCase()+'...';
try{{
var r=await fetch('/machine/camera_mode/'+m,{{method:'POST'}});
if(!r.ok)throw new Error(await r.text());
msg.className='msg ok';msg.textContent='\\u2713 '+m.toUpperCase();
a(m);
}}catch(e){{msg.className='msg err';msg.textContent='\\u2717 '+e.message}}
}}
async function refresh(){{
try{{
var r=await fetch('/machine/camera_mode/status');
var d=await r.json();
a(d.ir_mode&&d.ir_mode.short?d.ir_mode.short:'auto');
}}catch(e){{}}
}}
refresh();
</script>
</body>
</html>"""


def load_component(config):
    return CameraMode(config)
