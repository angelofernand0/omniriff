"""Local, accessible target display and portable saved report."""
import json


def page(report=None):
    initial = json.dumps(report).replace('<','\\u003c')
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OmniRiff · Gesture soundcheck</title><style>
:root{color-scheme:dark;font:18px/1.5 system-ui;background:#100f19;color:#f8f5ff}body{max-width:960px;margin:0 auto;padding:32px 24px}
small{letter-spacing:.12em;color:#f48db8;text-transform:uppercase}h1{font-size:clamp(30px,6vw,58px);margin:8px 0}p{color:#bfb9ce}
.panel{padding:28px;border:1px solid #53405d;background:#1c1727;border-radius:12px;margin:24px 0}.row{display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap}
.number{font-size:clamp(48px,10vw,90px);line-height:1.2}#cue{font-size:25px;color:#fff}.rail{height:30px;background:#363043;position:relative;margin:32px 0;border-radius:4px}
#fill{height:100%;width:0;background:#bd76ff;transition:width .12s}#target{position:absolute;top:-12px;height:54px;border-left:4px solid #fff;left:50%}
progress{width:100%;accent-color:#ef91ba;height:18px}li{padding:8px 0}#health{font-size:14px}button{font:inherit;color:#fff;background:#4a2856;border:1px solid #d590d6;padding:10px 18px;cursor:pointer}
svg{width:100%;height:200px;background:#17131f} .legend{font-size:14px} .passed{color:#a8efba}
</style><small>OmniRiff / Gesture soundcheck</small><h1>Grab. Move. Hold.</h1>
<p>A short rehearsal for your pinch control. Your guitar keeps running; this page sends no rig commands.</p>
<p id="source"></p><div class="panel"><div class="row"><div><small>Target</small><div class="number" id="goal">—</div></div><div><small>Actual filter</small><div class="number" id="actual">—</div></div></div>
<div class="rail" role="img" aria-label="Actual filter fill and target marker"><div id="fill"></div><div id="target"></div></div>
<div id="cue" role="status" aria-live="polite">Connecting…</div><p id="health">Waiting for feeds</p><progress id="progress" max="1" value="0" aria-label="Hold progress"></progress></div>
<div class="row"><h2 id="step">Three targets</h2><button id="download">Download current report</button></div><ol id="results"></ol>
<svg id="chart" viewBox="0 0 900 180" role="img" aria-label="Recorded filter and target over time"></svg>
<p class="legend">Purple: observed filter · white dashed: target. Gaps mean tracking/state was unavailable.</p>
<p>Keep the hand lit from the front. Pinch and move toward the target, hold it, then open your hand and hold the sound. At 100%, move down first. A missing hand does not count as a release.</p>
<p>This checks observed control behavior. It does not grade guitar skill, verify audio, or prove the hand feed came from a live camera.</p>
<script>
const saved=INITIAL; let current=saved;
const $=id=>document.getElementById(id), percent=v=>v==null?'—':Math.round(v*100)+'%';
function render(s){current=s;$('source').textContent=s.source_label||'Local rig: source unverified';$('goal').textContent=percent(s.target);$('actual').textContent=percent(s.value);$('fill').style.width=(s.value==null?0:s.value*100)+'%';$('target').style.left=(s.target==null?50:s.target*100)+'%';$('cue').textContent=s.cue;$('progress').value=s.progress;$('step').textContent=s.phase==='done'?'Results':`Target ${s.step} of ${s.total}`;$('health').textContent=(saved?'SAVED REPORT · ':s.complete?'COMPLETE · ':s.usable?'FRESH HAND + ENGINE · ':'WAITING / TRACKING LOST · ')+s.seconds+' s';$('results').replaceChildren();for(const r of s.results||[]){const li=document.createElement('li');li.textContent=`${percent(r.target)} — ${r.passed?'Completed':'Not completed'} (${r.seconds}s)`;if(r.passed)li.className='passed';$('results').append(li)}
 const trace=s.trace||[];if(trace.length){const max=Math.max(1,trace[trace.length-1].seconds);let line='',goal='',drawing=false;for(const p of trace){const x=p.seconds/max*900;goal+=(goal?'L':'M')+x+','+(170-p.target*160)+' ';if(p.usable&&p.value!=null){line+=(drawing?'L':'M')+x+','+(170-p.value*160)+' ';drawing=true}else drawing=false;}$('chart').innerHTML='';for(const [d,color,dash] of [[goal,'#eee','5 5'],[line,'#bd76ff','']]){const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d',d);path.setAttribute('fill','none');path.setAttribute('stroke',color);path.setAttribute('stroke-width','3');path.setAttribute('stroke-dasharray',dash);$('chart').append(path)}}}
$('download').onclick=()=>{if(!current)return;const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(current,null,2)],{type:'application/json'}));a.download='gesture-soundcheck.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};
async function poll(){try{const r=await fetch('/api/state',{cache:'no-store'});if(!r.ok)throw Error();render(await r.json())}catch(e){$('health').textContent='SOUNDCHECK DISCONNECTED — open saved report when finished'}finally{if(!current||!current.complete)setTimeout(poll,200)}}
if(saved)render(saved);else poll();
</script></html>'''.replace('INITIAL',initial)
