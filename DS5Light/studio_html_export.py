"""Standalone scoped profile page. All writes require an explicit Apply action."""
import json,html
from studio_scope import EDITABLE,LIGHTBAR_FIELDS,config_version
from studio_help import label

def profile_html(document):
    values={k:v for k,v in document['fields'].items() if k in EDITABLE and k!='macro_disable'}
    # Standalone legacy WebHID pages have no capability-gated lightbar writer.
    # Keep the fields in JSON, but block browser Apply for extended profiles.
    fields=[dict(key=k,id=EDITABLE[k][0],type=EDITABLE[k][2],value=v) for k,v in values.items()]
    data=json.dumps(dict(name=document.get('name','DS5Light Studio'),version=2,cfgVersion=config_version(values),fields=values,settings=values),ensure_ascii=False).replace('<','\\u003c')
    wire=json.dumps(fields,ensure_ascii=False).replace('<','\\u003c')
    rows=''.join('<tr><td>'+html.escape(label(k))+'</td><td>'+html.escape(k)+'</td><td>'+html.escape(str(v))+'</td></tr>' for k,v in values.items())
    return '''<!doctype html><meta charset="utf-8"><title>DS5Light Studio profile</title>
<style>body{background:#0b0b0b;color:#eee9df;font:15px system-ui;max-width:1000px;margin:40px auto;padding:24px}button{padding:12px;margin:6px;background:#d6ad52;border:0;cursor:pointer}td,th{padding:10px;border-bottom:1px solid #363126;text-align:left}table{width:100%}#status{padding:16px;color:#d6ad52}</style>
<h1>DS5Light Studio</h1><p>프로필 파일 · 제외된 옵션·공사 중 트리거·매크로 활성 선택은 전송하지 않습니다.</p>
<p>DS5Light와 Studio 설정을 닫고 사용하세요. 편집만으로 적용되지 않습니다. 적용 후 유지하려면 저장을 선택하세요.</p>
<button id="json">JSON 다운로드</button><button id="apply">연결 후 적용</button><button id="save">연결 후 적용·Pico에 저장</button><div id="status">대기</div>
<table><tr><th>설정</th><th>영문 이름</th><th>값</th></tr>'''+rows+'''</table><script>
const PROFILE='''+data+''';const FIELDS='''+wire+''';
const status=document.getElementById('status');let device=null,busy=false;
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function send(cmd,payload=[]){const p=new Uint8Array(63);p[0]=0x66;p[1]=cmd;p.set(payload,2);await device.sendFeatureReport(0x80,p);}
async function command(cmd,payload=[],fid=null){await send(cmd,payload);for(let i=0;i<12;i++){await delay(60);const r=new Uint8Array((await device.receiveFeatureReport(0x81)).buffer);if(r[0]!==0x81||r[1]!==0x66||r[2]!==cmd)continue;const b=r.slice(1);if(fid!==null&&b[2]!==fid)continue;return b;}throw Error('Studio 응답 시간 초과');}
function bytes(f){const a=new Uint8Array(f.type==='u8'?1:f.type==='u16'?2:4),v=new DataView(a.buffer);if(f.type==='u8')v.setUint8(0,f.value);else if(f.type==='u16')v.setUint16(0,f.value,true);else if(f.type==='u32')v.setUint32(0,f.value,true);else v.setFloat32(0,f.value,true);return a;}
async function apply(save){if(busy)return;busy=true;for(const b of document.querySelectorAll('button'))b.disabled=true;let changed=false;
try{if(!navigator.hid)throw Error('WebHID를 지원하는 브라우저가 필요합니다.');
if(FIELDS.some(f=>['lightbar_fixed','lightbar_rgb','rumble_gain','rumble_release','usb_gamepad_mode'].includes(f.key)))throw Error('펌웨어 확장 설정이 포함된 프로필은 DS5Light 앱에서 적용하세요. JSON 다운로드는 사용할 수 있습니다.');
const ds=await navigator.hid.requestDevice({filters:[{vendorId:0x054c,productId:0x0ce6},{vendorId:0x054c,productId:0x0df2}]});if(!ds.length)return;device=ds[0];if(!device.opened)await device.open();
const cfg=await command(4,[0],0);if(cfg[3]!==19)throw Error('지원하는 Studio cfgVersion 19가 아닙니다.');
if(!confirm('파일의 설정을 현재 연결에 적용'+(save?'하고 Pico에 저장':'')+'할까요?'))return;
for(const f of FIELDS){status.textContent='적용 중 · '+f.key;const data=bytes(f),r=await command(1,[f.id,...data]);changed=true;if(r[2]!==0)throw Error('설정 적용 실패: '+f.key);const read=await command(4,[f.id],f.id);if(data.some((v,i)=>v!==read[3+i]))throw Error('적용값 불일치: '+f.key);}
if(save){await send(2);await delay(400);}
status.textContent=save?'적용 확인 · 저장 요청 완료. 영구 유지 여부는 재연결 후 확인하세요.':'적용 확인 · 전원을 끄면 유지되지 않을 수 있습니다.';
if(confirm('USB 설정 반영을 위해 Pico를 다시 연결할까요?'))await send(3);
}catch(e){status.textContent=(changed?'일부 값이 적용되었을 수 있습니다. 다시 읽어 확인하세요. ':'')+e.message;}
finally{if(device&&device.opened)await device.close().catch(()=>{});device=null;busy=false;for(const b of document.querySelectorAll('button'))b.disabled=false;}}
document.getElementById('apply').onclick=()=>apply(false);document.getElementById('save').onclick=()=>apply(true);
document.getElementById('json').onclick=()=>{const u=URL.createObjectURL(new Blob([JSON.stringify(PROFILE,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download='DS5Light-profile.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);};
</script>'''
