export const config = {
  width: 960, height: 540, characterHeight: 0.04, videoStart: 1,
  desk: { normal: [-0.0168397825, -0.0671243837, 0.9976024954], offset: 0.0084577321 },
  laptop: { width: 0.3126, depth: 0.2212, top: 0 },
  cup: { x: -0.06338986, y: 0.2171216, base: 0.00506108, height: 0.1185636, radius: 0.0393455 },
  lighting: { color: 0xfff3db, intensity: 3.0, direction: [-0.35,-0.3,1.2], ambient: 1.8, shadowOpacity: 0.24 },
  movement: { walkSpeed: 0.045, runSpeed: 0.11, stepPeriod: 0.36, jumpHeight: 0.014, hopDuration: 0.52 },
  demo: { duration: 68, events: [[2,'walk'],[11,'sit'],[19,'climb'],[38,'message'],[48,'permission'],[52,'allow'],[57,'urgent']] as [number,string][] },
  colors: { head: 0xf5bd7e, body: 0x78cbbd, cream: 0xfff1d2, coral: 0xf6856e, eyes: 0x211811 },
};
