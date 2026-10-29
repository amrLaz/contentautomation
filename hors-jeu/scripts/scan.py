import cv2, sys, numpy as np, subprocess
sys.path.insert(0,'.')
from detect import Detector
V='/root/.claude/uploads/e92ffead-68d8-55b5-af9d-c3d5e17a2339/3efed0dd-ScreenRecording_10-30-2026_00-42-02_1.mp4'
d=Detector('/tmp/claude-0/hjmodels/yolox.onnx')
def team(im, b):
    x0,y0,x1,y1=[int(v) for v in b]; h=y1-y0
    c=im[y0+int(h*.15):y0+int(h*.55), x0+int((x1-x0)*.2):x1-int((x1-x0)*.2)]
    if c.size==0: return '?'
    hsv=cv2.cvtColor(c,cv2.COLOR_BGR2HSV).reshape(-1,3); m=hsv[(hsv[:,1]>70)&(hsv[:,2]>60)]
    if len(m)<8: return '?'
    hue=np.median(m[:,0])
    return 'red' if (hue<19 or hue>165) else ('green' if 38<hue<95 else 'gk' if 19<=hue<=38 else '?')
t0,t1,fps=float(sys.argv[1]),float(sys.argv[2]),float(sys.argv[3]); out=sys.argv[4]
tiles=[]
n=int((t1-t0)*fps)
for k in range(n):
    t=t0+k/fps
    png=subprocess.run(['ffmpeg','-v','error','-ss',f'{t:.3f}','-i',V,'-frames:v','1','-f','image2pipe','-vcodec','png','-'],capture_output=True).stdout
    im=cv2.imdecode(np.frombuffer(png,np.uint8),1)[180:1260]
    r=d(im,y0=200)
    for x in r:
        b=[int(v) for v in x['box']]
        if x['cls']=='ball': col=(255,0,255)
        else:
            tm=team(im,b); col={'red':(0,0,255),'green':(0,200,0),'gk':(0,200,255),'?':(200,200,200)}[tm]
        cv2.rectangle(im,(b[0],b[1]),(b[2],b[3]),col,3)
    cv2.putText(im,f'{t:.2f}s',(40,1040),cv2.FONT_HERSHEY_SIMPLEX,2.2,(255,255,255),5)
    tiles.append(cv2.resize(im,(640,360)))
cols=3; rows=(len(tiles)+cols-1)//cols
while len(tiles)<rows*cols: tiles.append(np.zeros_like(tiles[0]))
sheet=np.vstack([np.hstack(tiles[r*cols:(r+1)*cols]) for r in range(rows)])
cv2.imwrite(out,sheet)
