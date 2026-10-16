import * as THREE from 'three';
import { Bricki, type Pose } from './avatar';
import { config } from './config';
import './style.css';

type CameraSample={t:number;K:number[][];c2w:number[][];matrix?:THREE.Matrix4};
type Card={kind:string;title:string;body:string;time:number;permission?:boolean};
const canvas=document.querySelector<HTMLCanvasElement>('#stage')!;
const ctx=canvas.getContext('2d',{alpha:false})!;
const W=1920,H=1080;
const stateOutput=document.querySelector<HTMLOutputElement>('#state')!;
const video=document.createElement('video');video.src='/scene/desk.mp4';video.preload='auto';video.muted=true;video.playsInline=true;
const renderer=new THREE.WebGLRenderer({alpha:true,antialias:true,preserveDrawingBuffer:true});
renderer.setSize(W,H);renderer.setPixelRatio(1);renderer.setClearColor(0,0);renderer.outputColorSpace=THREE.SRGBColorSpace;
renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.08;
renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(50,W/H,.01,10);
camera.matrixAutoUpdate=false;
const ambient=new THREE.HemisphereLight(0xfff4df,0x75896e,config.lighting.ambient);ambient.position.set(0,0,1);scene.add(ambient);
const light=new THREE.DirectionalLight(config.lighting.color,config.lighting.intensity);
light.position.set(...config.lighting.direction as [number,number,number]);light.target.position.set(.1,.1,0);scene.add(light,light.target);
light.castShadow=true;light.shadow.mapSize.set(2048,2048);light.shadow.camera.left=-.7;light.shadow.camera.right=.7;light.shadow.camera.top=.7;light.shadow.camera.bottom=-.7;light.shadow.camera.near=.1;light.shadow.camera.far=3;light.shadow.normalBias=.0005;light.shadow.bias=-.00003;
const normal=new THREE.Vector3(...config.desk.normal as [number,number,number]).normalize();
function deskZ(x:number,y:number){return -(normal.x*x+normal.y*y+config.desk.offset)/normal.z;}
const surface=new THREE.Mesh(new THREE.PlaneGeometry(1.4,1.2),new THREE.ShadowMaterial({opacity:config.lighting.shadowOpacity}));
surface.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1),normal);surface.position.z=deskZ(0,0)+.0001;surface.receiveShadow=true;scene.add(surface);
const laptopSurface=new THREE.Mesh(new THREE.PlaneGeometry(config.laptop.width,config.laptop.depth),new THREE.ShadowMaterial({opacity:.22}));laptopSurface.position.set(config.laptop.width/2,config.laptop.depth/2,.0002);laptopSurface.receiveShadow=true;scene.add(laptopSurface);
const occluderMat=new THREE.MeshBasicMaterial({colorWrite:false,depthWrite:true,side:THREE.DoubleSide});
const proxies:THREE.Mesh[]=[];
function proxy(geometry:THREE.BufferGeometry,position:number[]){const mesh=new THREE.Mesh(geometry,occluderMat);mesh.position.set(...position as [number,number,number]);mesh.renderOrder=-10;scene.add(mesh);proxies.push(mesh);return mesh;}
proxy(new THREE.BoxGeometry(config.laptop.width,config.laptop.depth,.009),[config.laptop.width/2,config.laptop.depth/2,-.0046]);
const cup=config.cup, cupTop=cup.base+cup.height;
const cupMesh=proxy(new THREE.CylinderGeometry(cup.radius,cup.radius*.78,cup.height,64,1,false),[cup.x,cup.y,cup.base+cup.height/2]);cupMesh.rotation.x=Math.PI/2;
const lid=proxy(new THREE.CylinderGeometry(cup.radius*1.015,cup.radius*1.015,.003,64),[cup.x,cup.y,cupTop+.001]);lid.rotation.x=Math.PI/2;
const cupShadow=new THREE.Mesh(new THREE.CircleGeometry(cup.radius,64),new THREE.ShadowMaterial({opacity:.25}));cupShadow.position.set(cup.x,cup.y,cupTop+.0027);cupShadow.receiveShadow=true;scene.add(cupShadow);
const avatar=new Bricki();scene.add(avatar.root);avatar.root.position.set(.14,-.043,deskZ(.14,-.043));
const debugGroup=new THREE.Group();scene.add(debugGroup);debugGroup.visible=false;
const grid=new THREE.GridHelper(1,100,0x74bba7,0x5b8c77);grid.rotation.x=Math.PI/2;grid.position.z=deskZ(0,0)+.0002;debugGroup.add(grid);
for(const p of proxies){const edges=new THREE.LineSegments(new THREE.EdgesGeometry(p.geometry),new THREE.LineBasicMaterial({color:0x63bfa9,transparent:true,opacity:.7}));edges.position.copy(p.position);edges.rotation.copy(p.rotation);debugGroup.add(edges);}

let started=false,clockStart=0,mode='idle',modeStart=0,from=avatar.root.position.clone(),card:Card|null=null;
let guidedStart:number|null=null,guidedIndex=0,recording=false,recorder:MediaRecorder|null=null,chunks:Blob[]=[];
let latestMediaTime=config.videoStart,showTech=false,lastFootstep=0,talkingUntil=0;
let audioContext:AudioContext|null=null,audioDestination:MediaStreamAudioDestinationNode|null=null;
const buffers=new Map<string,AudioBuffer>();
const samples:CameraSample[]=(await fetch('/scene/cameras.json').then(r=>r.json())).frames;
samples.forEach(s=>{s.matrix=new THREE.Matrix4().fromArray(s.c2w.flat()).transpose();});
const cvFlip=new THREE.Matrix4().makeScale(1,-1,-1);
let frameIndex=0;
const lines:Record<string,{title:string;body:string;audio:string}>= {
  message:{title:'A message for you',body:'Your teammate: “Ready when you are!”',audio:'message'},
  permission:{title:'Camera access?',body:'Your assistant is asking for permission.',audio:'permission'},
  urgent:{title:'Your meeting starts in 1 minute',body:'Time to wrap up. I’ll come with you.',audio:'urgent'},
  allow:{title:'You’re in control',body:'Permission allowed. Thanks!',audio:'allow'},
  later:{title:'No rush',body:'Not now. I’ll leave it for later.',audio:'later'},
};
const captureState={mode,frame:0,characterHeight:avatar.height,events:[] as {time:number;action:string}[],recording:false};
Object.assign(window,{deskBuddyState:captureState});

async function initializeAudio(){
  audioContext??=new AudioContext();await audioContext.resume();
  audioDestination??=audioContext.createMediaStreamDestination();
  await Promise.all(['intro','message','permission','urgent','allow','later'].map(async id=>{
    if(buffers.has(id))return;
    try{const r=await fetch('/audio/'+id+'.wav');if(r.ok)buffers.set(id,await audioContext!.decodeAudioData(await r.arrayBuffer()));}catch{ /* A missing voice asset never stops the live animation. */ }
  }));
}
function speak(id:string){
  if(!audioContext||!buffers.has(id)||!audioDestination)return;
  const source=audioContext.createBufferSource();source.buffer=buffers.get(id)!;source.playbackRate.value=1.08;
  const gain=audioContext.createGain();gain.gain.value=.85;source.connect(gain);gain.connect(audioContext.destination);gain.connect(audioDestination);source.start();
  talkingUntil=performance.now()+source.buffer.duration/1.08*1000;
}
function sound(frequency:number,volume=.035){
  if(!audioContext||!audioDestination)return;
  const osc=audioContext.createOscillator(),gain=audioContext.createGain(),pan=audioContext.createStereoPanner();
  osc.type='triangle';osc.frequency.setValueAtTime(frequency,audioContext.currentTime);osc.frequency.exponentialRampToValueAtTime(frequency*.4,audioContext.currentTime+.045);
  gain.gain.setValueAtTime(volume,audioContext.currentTime);gain.gain.exponentialRampToValueAtTime(.0001,audioContext.currentTime+.065);
  pan.pan.value=THREE.MathUtils.clamp((avatar.root.position.x-.15)*3,-.7,.7);osc.connect(gain);gain.connect(pan);pan.connect(audioContext.destination);pan.connect(audioDestination);osc.start();osc.stop(audioContext.currentTime+.075);
}
function currentTime(){return started?(performance.now()-clockStart)/1000:0;}
async function start(){
  if(started)return;
  await initializeAudio();video.currentTime=config.videoStart;await video.play();
  started=true;clockStart=performance.now();avatar.root.visible=true;document.querySelector<HTMLButtonElement>('#start')!.hidden=true;
  speak('intro');setAction('idle');
}
function setAction(action:string){
  if(!started&&action!=='idle')void start();
  if((action==='allow'||action==='later')&&!card?.permission)return;
  from=avatar.root.position.clone();mode=action;modeStart=currentTime();
  captureState.mode=mode;captureState.events.push({time:modeStart,action});
  document.querySelectorAll<HTMLButtonElement>('[data-action]').forEach(b=>b.classList.toggle('active',b.dataset.action===action));
  stateOutput.value=action==='idle'?'Bricki is here':action==='climb'?'Climbing the actual cup':action==='cup-sit'?'Resting on the cup':action==='allow'?'Allowed by you':action==='later'?'Deferred by you':action.charAt(0).toUpperCase()+action.slice(1);
  if(lines[action]){card={kind:action,title:lines[action].title,body:lines[action].body,time:modeStart,permission:action==='permission'};speak(lines[action].audio);sound(action==='urgent'?920:660,.06);}else card=null;
}
function vec(x:number,y:number,z=deskZ(x,y)){return new THREE.Vector3(x,y,z);}
function smooth(t:number){return THREE.MathUtils.smoothstep(THREE.MathUtils.clamp(t,0,1),0,1);}
function lerpPath(points:THREE.Vector3[],phase:number){
  const lengths=points.slice(1).map((p,i)=>p.distanceTo(points[i]));const total=lengths.reduce((a,b)=>a+b,0);let dist=THREE.MathUtils.clamp(phase,0,1)*total;
  for(let i=0;i<lengths.length;i++){if(dist<=lengths[i])return points[i].clone().lerp(points[i+1],lengths[i]?dist/lengths[i]:0);dist-=lengths[i];}
  return points.at(-1)!.clone();
}
function animateCharacter(t:number){
  const age=t-modeStart,old=avatar.root.position.clone(),scale=avatar.height/.04;
  let p=old.clone(),pose:Pose={kind:mode,moving:false,run:false,age},jump=0,heading=0;
  if(mode==='idle'||mode==='allow'||mode==='later'){
    p.copy(from);if(mode!=='idle'){p.lerp(vec(.14,-.043),smooth(age/.6));}pose.excited=mode==='allow'&&age<2;
    if(mode==='allow')heading=Math.min(1,age/1.2)*Math.PI*2;
  }else if(mode==='walk'){
    const phase=(age%10)/10;const points=[vec(.14,-.043),vec(-.035,-.043),vec(-.055,.03),vec(-.035,-.043),vec(.14,-.043)];p=lerpPath(points,phase);pose.moving=true;
  }else if(mode==='sit'){
    const target=vec(.027,-.004,-.009*scale);p.copy(from).lerp(target,smooth(age/1.5));if(age<1.5){p.z+=Math.sin(Math.PI*age/1.5)*.014;pose.moving=true;}else pose.kind='sit';
  }else if(mode==='climb'){
    const front=cup.y-cup.radius-.006;
    if(age<4){p=lerpPath([from,vec(-.055,-.028),vec(cup.x,front-.025)],smooth(age/4));pose.moving=true;}
    else if(age<4.65){p=vec(cup.x,front-.025);p.z-=Math.sin((age-4)/.65*Math.PI)*.002;heading=Math.PI;}
    else if(age<5.35){const u=(age-4.65)/.7;p=vec(cup.x,THREE.MathUtils.lerp(front-.025,front,u));p.z=THREE.MathUtils.lerp(deskZ(cup.x,front),cupTop-.031*scale,u)+Math.sin(Math.PI*u)*.018;pose.hang=true;heading=Math.PI;jump=.01;}
    else if(age<6.8){p=vec(cup.x,front,cupTop-.031*scale);pose.hang=true;heading=Math.PI;}
    else if(age<8.4){const u=smooth((age-6.8)/1.6);p=vec(cup.x,THREE.MathUtils.lerp(front,cup.y-cup.radius*.74,u),THREE.MathUtils.lerp(cupTop-.031*scale,cupTop+.004,u));pose.hang=true;heading=Math.PI;}
    else if(age<10.5){p=vec(cup.x,cup.y-cup.radius*.74,cupTop+.004);pose.excited=true;}
    else{p=vec(cup.x,cup.y-cup.radius-.001,cupTop-.009*scale);pose.kind='cup-sit';}
  }else if(mode==='message'||mode==='permission'||mode==='urgent'){
    const target=vec(.14,-.043);
    if(age<1.5){const u=smooth(age/1.5);p.copy(from).lerp(target,u);p.z+=Math.sin(Math.PI*u)*Math.min(.035,Math.max(.014,from.z+.012));pose.moving=true;pose.run=true;}
    else{
      p=target;const elapsed=age-1.5,period=mode==='urgent'?.42:.65,cycles=mode==='message'?2:mode==='urgent'?5:3;
      if(elapsed<period*cycles){const phase=(elapsed%period)/period;jump=Math.sin(Math.PI*phase)*(mode==='urgent'?.022:.014);p.z+=jump;if(phase>.94&&t-lastFootstep>.18){sound(230,.055);lastFootstep=t;}}
      pose.excited=true;
    }
  }
  if(pose.moving){const dx=p.x-old.x,dy=p.y-old.y;if(Math.hypot(dx,dy)>1e-6)heading=Math.atan2(dx,-dy);if(t-lastFootstep>(pose.run?.17:.3)){sound(340,.02);lastFootstep=t;}}
  avatar.root.position.copy(p);avatar.root.rotation.z=heading;pose.jump=jump;avatar.animate(t,pose);
  if(performance.now()<talkingUntil)avatar.head.scale.z=1+Math.sin(t*25)*.018;
}

function syncCamera(time:number){
  let left=0,right=samples.length-1;
  while(left<right){const mid=Math.ceil((left+right)/2);if(samples[mid].t<=time+.0005)left=mid;else right=mid-1;}
  frameIndex=left;const s=samples[left],K=s.K,near=.01,far=10;
  camera.matrix.copy(s.matrix!).multiply(cvFlip);camera.updateMatrixWorld(true);camera.matrixWorldInverse.copy(camera.matrixWorld).invert();
  const fx=K[0][0],fy=K[1][1],cx=K[0][2],cy=K[1][2],w=config.width,h=config.height;
  camera.projectionMatrix.set(2*fx/w,0,1-2*cx/w,0,0,2*fy/h,2*cy/h-1,0,0,0,-(far+near)/(far-near),-2*far*near/(far-near),0,0,-1,0);
  camera.projectionMatrixInverse.copy(camera.projectionMatrix).invert();captureState.frame=left;
}
function screen(point:THREE.Vector3){const p=point.clone().project(camera);return {x:(p.x+1)/2*W,y:(1-p.y)/2*H};}
function round(x:number,y:number,w:number,h:number,r:number,fill:string){ctx.fillStyle=fill;ctx.beginPath();ctx.roundRect(x,y,w,h,r);ctx.fill();}
function text(value:string,x:number,y:number,size:number,color='#f4f9ed',weight='400'){ctx.font=`${weight} ${size}px "DM Sans",system-ui,sans-serif`;ctx.fillStyle=color;ctx.fillText(value,x,y);}
function drawOverlay(t:number){
  const p=screen(avatar.root.position.clone().add(new THREE.Vector3(0,0,avatar.height+.009)));
  if(card){
    const w=452,h=card.permission?195:134,x=THREE.MathUtils.clamp(p.x-w/2,25,W-w-25),y=THREE.MathUtils.clamp(p.y-h-35,100,H-h-90);
    round(x,y,w,h,16,'rgba(18,43,35,.90)');ctx.strokeStyle='rgba(160,235,198,.65)';ctx.lineWidth=1.5;ctx.beginPath();ctx.roundRect(x,y,w,h,16);ctx.stroke();
    text(card.kind==='urgent'?'!':'✦',x+20,y+36,26,'#d3eeba');text(card.title,x+57,y+37,25,'#eff7e5','600');text(card.body,x+23,y+80,19,'#bdd6c8');
    if(card.permission){round(x+20,y+115,198,52,9,'#c8e7b6');text('Allow  ↵',x+72,y+149,22,'#193320','600');round(x+234,y+115,198,52,9,'rgba(255,255,255,.08)');text('Later',x+302,y+149,22,'#e0eada');}
    ctx.strokeStyle='rgba(170,233,205,.6)';ctx.beginPath();ctx.moveTo(THREE.MathUtils.clamp(p.x,x+25,x+w-25),y+h);ctx.lineTo(p.x,p.y);ctx.stroke();
  }
  round(24,24,284,64,13,'rgba(15,32,25,.79)');text('DESK BUDDY',45,65,28,'#eff5dc','600');
  round(W-271,24,247,59,12,'rgba(15,32,25,.72)');ctx.fillStyle='#c5edb0';ctx.beginPath();ctx.arc(W-243,53,5,0,Math.PI*2);ctx.fill();text('Bricki · '+(avatar.height*100).toFixed(0)+' cm',W-225,61,23,'#e2efd8');
  if(guidedStart!==null){
    const captions:Record<string,string>={idle:'A tiny companion on your real desk.',walk:'Walking with the camera moving. Four centimeters tall.',sit:'A place to rest. Feet over the laptop edge.',climb:'Jump. Grab. Hang. Pull up. Settle on the cup.',message:'A message becomes a small, physical interruption.',permission:'Your companion asks. You stay in control.',allow:'One tap to allow. A little celebration.',later:'Not now. Bricki understands.',urgent:'One minute to your meeting — this one matters.'};
    const message=captions[mode]||'';ctx.font='24px "DM Sans",system-ui';const width=ctx.measureText(message).width;
    round((W-width)/2-30,H-90,width+60,55,12,'rgba(16,33,26,.85)');text(message,(W-width)/2,H-54,24,'#edf4e6');
    if(recording){round(24,H-66,178,39,9,'rgba(28,35,29,.8)');ctx.fillStyle='#fbad99';ctx.beginPath();ctx.arc(43,H-46,4,0,Math.PI*2);ctx.fill();text('LIVE SESSION',57,H-39,17,'#e2ece0','600');}
  }
  if(debugGroup.visible){round(26,107,445,111,12,'rgba(13,29,23,.88)');text('Surface check',44,141,23,'#cde4b6','600');text(`Frame ${frameIndex} · ${latestMediaTime.toFixed(3)} s`,44,176,19,'#c2d4c8');text('Metric scene · 1 cm grid · proxy occlusion',44,203,17,'#93b09f');}
  if(showTech){round(W-602,106,577,304,15,'rgba(13,29,23,.92)');['RUNNING IN THIS BROWSER','Procedural 3D character · live animation','506 synchronized camera samples','Recorded desk footage · metric laptop anchor','Nano Banana: original character design','No generated avatar video in this player','Keys 1–6 · Enter: allow · G: surfaces'].forEach((line,i)=>text(line,W-578,145+i*36,i===0?22:19,i===0?'#d6eabc':'#b9cfc2',i===0?'600':'400'));}
  if(!started){round(0,0,W,H,0,'rgba(13,26,19,.15)');}
}
function tick(now:number){
  const t=currentTime();
  if(started&&video.currentTime>video.duration-.07)video.currentTime=config.videoStart;
  const media=Math.abs(video.currentTime-latestMediaTime)>.08?video.currentTime:latestMediaTime;syncCamera(media||config.videoStart);
  if(guidedStart!==null){const elapsed=t-guidedStart;while(guidedIndex<config.demo.events.length&&elapsed>=config.demo.events[guidedIndex][0])setAction(config.demo.events[guidedIndex++][1]);if(elapsed>config.demo.duration){if(recording)stopRecording();else{guidedStart=null;stateOutput.value='Guided demo finished — try the controls';}}}
  if(started)animateCharacter(t);
  renderer.render(scene,camera);
  ctx.fillStyle='#19291d';ctx.fillRect(0,0,W,H);if(video.readyState>=2)ctx.drawImage(video,0,0,W,H);ctx.drawImage(renderer.domElement,0,0,W,H);drawOverlay(t);
  captureState.recording=recording;captureState.characterHeight=avatar.height;
  requestAnimationFrame(tick);
}
function guided(){from=vec(.14,-.043);avatar.root.position.copy(from);setAction('idle');guidedStart=currentTime();guidedIndex=0;card=null;}
function stopRecording(){if(recorder&&recorder.state==='recording')recorder.stop();recording=false;guidedStart=null;document.querySelector<HTMLButtonElement>('#record')!.textContent='Record live demo';stateOutput.value='Recording ready — download below';}
async function record(){
  await start();if(recording){stopRecording();return;}
  await initializeAudio();chunks=[];
  const stream=canvas.captureStream(30);if(audioDestination)audioDestination.stream.getAudioTracks().forEach(track=>stream.addTrack(track));
  const mime=MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus')?'video/webm;codecs=vp9,opus':'video/webm';
  recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:10000000});
  recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};recorder.onstop=()=>{
    const blob=new Blob(chunks,{type:mime}),link=document.querySelector<HTMLAnchorElement>('#download')!;link.href=URL.createObjectURL(blob);link.download='DeskBuddy_Live_Demo.webm';link.hidden=false;
    Object.assign(window,{deskBuddyRecording:{bytes:blob.size,events:captureState.events.slice()}});
  };
  recorder.start(1000);recording=true;document.querySelector<HTMLButtonElement>('#record')!.textContent='Stop recording';guided();
}
document.querySelector('#start')!.addEventListener('click',()=>void start());
document.querySelectorAll<HTMLButtonElement>('[data-action]').forEach(b=>b.onclick=()=>setAction(b.dataset.action!));
document.querySelector<HTMLButtonElement>('#guided')!.onclick=async()=>{await start();guided();};
document.querySelector<HTMLButtonElement>('#record')!.onclick=()=>void record();
document.querySelector<HTMLButtonElement>('#pause')!.onclick=()=>{if(video.paused){void video.play();document.querySelector('#pause')!.textContent='Pause footage';}else{video.pause();document.querySelector('#pause')!.textContent='Resume footage';}};
document.querySelector<HTMLButtonElement>('#debug')!.onclick=()=>debugGroup.visible=!debugGroup.visible;
window.addEventListener('keydown',event=>{
  const actions:Record<string,string>={'1':'walk','2':'sit','3':'climb','4':'message','5':'permission','6':'urgent','Enter':'allow','Backspace':'later'};
  if(actions[event.key]){event.preventDefault();setAction(actions[event.key]);}
  if(event.key.toLowerCase()==='g')debugGroup.visible=!debugGroup.visible;
  if(event.key==='F1'){event.preventDefault();showTech=!showTech;}
  if(event.key==='-'){avatar.setSize(.025);stateOutput.value='Tiny mode · 2.5 cm';}
  if(event.key==='+'){avatar.setSize(.04);stateOutput.value='Original size · 4 cm';}
});
canvas.addEventListener('click',event=>{if(!card?.permission)return;const rect=canvas.getBoundingClientRect(),x=(event.clientX-rect.left)/rect.width*W;
  const p=screen(avatar.root.position.clone().add(new THREE.Vector3(0,0,avatar.height+.009))),cx=THREE.MathUtils.clamp(p.x-226,25,W-477);setAction(x<cx+226?'allow':'later');});
video.addEventListener('loadeddata',()=>{video.currentTime=config.videoStart;});
if('requestVideoFrameCallback' in video){const callback=(_now:number,meta:VideoFrameCallbackMetadata)=>{latestMediaTime=meta.mediaTime;video.requestVideoFrameCallback(callback);};video.requestVideoFrameCallback(callback);}
avatar.root.visible=false;requestAnimationFrame(tick);
