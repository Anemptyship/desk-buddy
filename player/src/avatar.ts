import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { config } from './config';

export type Pose = { kind:string; moving:boolean; run:boolean; age:number; excited?:boolean; hang?:boolean; jump?:number };

export class Bricki {
  root = new THREE.Group();
  body = new THREE.Group();
  head = new THREE.Group();
  arms = [new THREE.Group(),new THREE.Group()];
  legs = [new THREE.Group(),new THREE.Group()];
  eyes:THREE.Mesh[]=[];
  shadow:THREE.Mesh;
  height = config.characterHeight;
  private plastic(color:number) { return new THREE.MeshPhysicalMaterial({color, roughness:.28, metalness:0, clearcoat:1,clearcoatRoughness:.2,ior:1.47}); }
  private mesh(geometry:THREE.BufferGeometry,material:THREE.Material,parent:THREE.Object3D,position:number[]) {
    const mesh=new THREE.Mesh(geometry,material);mesh.position.set(...position as [number,number,number]);mesh.castShadow=true;mesh.receiveShadow=true;parent.add(mesh);return mesh;
  }
  constructor() {
    const c=config.colors, mint=this.plastic(c.body),cream=this.plastic(c.cream),head=this.plastic(c.head), eye=this.plastic(c.eyes),coral=this.plastic(c.coral);
    this.root.name='Bricki — original procedural character, 0.04 meters';this.root.add(this.body);
    this.mesh(new RoundedBoxGeometry(.015,.009,.014,3,.003),mint,this.body,[0,0,.018]);
    this.mesh(new RoundedBoxGeometry(.0041,.00045,.004,2,.0006),coral,this.body,[0,-.0047,.019]);
    this.head.position.z=.0325;this.body.add(this.head);
    this.mesh(new RoundedBoxGeometry(.018,.013,.015,5,.004),head,this.head,[0,0,0]);
    [-1,1].forEach((s,i)=>{
      const e=this.mesh(new THREE.SphereGeometry(.00125,16,12),eye,this.head,[s*.0035,-.00665,.0013]);e.scale.y=.45;this.eyes.push(e);
      const cheek=this.mesh(new THREE.SphereGeometry(.0011,12,8),new THREE.MeshStandardMaterial({color:0xe89c7c,transparent:true,opacity:.46,roughness:.6}),this.head,[s*.0052,-.0065,-.0008]);cheek.scale.set(1,.12,.6);
      const arm=this.arms[i];arm.position.set(s*.009,0,.022);this.body.add(arm);
      this.mesh(new RoundedBoxGeometry(.0035,.004,.008,3,.0014),mint,arm,[0,0,-.0036]);
      this.mesh(new THREE.SphereGeometry(.0025,14,10),mint,arm,[0,0,-.009]);
      const leg=this.legs[i];leg.position.set(s*.0038,0,.012);this.root.add(leg);
      this.mesh(new RoundedBoxGeometry(.004,.0045,.0065,2,.001),cream,leg,[0,0,-.003]);
      this.mesh(new RoundedBoxGeometry(.0053,.007,.004,3,.0012),cream,leg,[0,-.0012,-.0095]);
    });
    const smile=new THREE.CatmullRomCurve3([new THREE.Vector3(-.002,-.00685,-.002),new THREE.Vector3(-.001,-.00705,-.0028),new THREE.Vector3(.001,-.00705,-.0028),new THREE.Vector3(.002,-.00685,-.002)]);
    this.mesh(new THREE.TubeGeometry(smile,16,.00022,6,false),eye,this.head,[0,0,0]);
    const seam=new THREE.Mesh(new THREE.TorusGeometry(.0066,.000045,3,48),new THREE.MeshStandardMaterial({color:c.head,roughness:.7}));seam.scale.set(1.18,.86,1);seam.position.z=-.0045;this.head.add(seam);
    this.shadow=new THREE.Mesh(new THREE.CircleGeometry(.009,24),new THREE.MeshBasicMaterial({color:0x182219,transparent:true,opacity:.13,depthWrite:false}));this.shadow.position.z=.0003;this.shadow.scale.y=.65;this.root.add(this.shadow);
  }
  setSize(height:number) { this.height=height;this.root.scale.setScalar(height/.04); }
  animate(time:number,pose:Pose) {
    const breath=(Math.sin(time*1.85)+1)*.0075;
    this.body.scale.z=1+breath;this.body.position.z=Math.sin(time*3.1)*.00013;
    this.body.rotation.y=Math.sin(time*1.23)*.012;
    this.head.rotation.z=Math.sin(time*.8)*.09;this.head.rotation.y=Math.sin(time*1.1)*.035;
    const blink=(time%3.7<.105)||(time%11.1>6.1&&time%11.1<6.18);
    this.eyes.forEach(e=>e.scale.z=blink?.08:1);
    this.arms.forEach(a=>{a.rotation.set(0,0,0);});this.legs.forEach(l=>{l.rotation.set(0,0,0);l.position.z=.012;});
    this.shadow.visible=!pose.hang&&(pose.jump||0)<.003;
    if(pose.moving){
      const phase=time*(pose.run?21:14);
      this.legs.forEach((leg,i)=>{
        const swing=Math.sin(phase+i*Math.PI);leg.rotation.x=swing*(pose.run?.58:.36);
        // Bring the bottom of the rigid toy foot back to the support plane in stance.
        if(swing<0)leg.position.z=.012-Math.max(0,(1-Math.cos(leg.rotation.x))*.0115);
        this.arms[i].rotation.x=-swing*(pose.run?.8:.40);
      });
      this.body.rotation.x=pose.run?-.13:-.025;
    }else this.body.rotation.x=0;
    if(pose.kind==='sit'||pose.kind==='cup-sit'){
      this.legs.forEach((leg,i)=>{leg.rotation.x=-.66+Math.sin(time*3+i*.8)*.13;});
      this.arms[0].rotation.y=.16;this.arms[1].rotation.y=-.16;
      this.head.rotation.x=Math.sin(time*.75)*.06;
    }
    if(pose.hang){
      this.arms.forEach(a=>a.rotation.x=-2.65);
      this.legs.forEach((leg,i)=>leg.rotation.x=Math.sin(time*18+i*Math.PI)*.6);
      this.body.rotation.x=-.18;
    }
    if(pose.excited||pose.kind==='wave'){
      this.arms[1].rotation.y=-2.1+Math.sin(time*16)*.27;this.arms[1].rotation.x=-.25;
      this.head.rotation.z=Math.sin(time*6)*.08;
    }
    if(pose.kind==='allow'){this.arms[1].rotation.y=-1.2;this.arms[1].rotation.x=-1.2;}
    if(pose.kind==='later'){this.arms.forEach((a,i)=>a.rotation.y=(i?1:-1)*.12);this.head.rotation.x=.18;}
    if((pose.jump||0)>.001){this.legs.forEach(l=>l.rotation.x=-.2);this.arms.forEach((a,i)=>a.rotation.y=(i?-1:1)*1.0);}
  }
}
