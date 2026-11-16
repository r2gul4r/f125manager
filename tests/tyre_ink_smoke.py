"""Measure the painted letters against the painted rings in Chrome."""
import base64
import sys

from playwright.sync_api import sync_playwright


def measure(page):
    page.wait_for_selector(".tyre-history .tyre-badge[data-compound]")
    page.evaluate("""async () => {
        await document.fonts.ready;
        const template = document.querySelector('.tyre-history .tyre-badge[data-compound]');
        const board = document.createElement('div');
        board.id = 'ink-test';
        board.style.cssText = 'position:fixed;inset:0 auto auto 0;z-index:10000;background:#111216;display:grid;grid-template-columns:repeat(5,96px);grid-auto-rows:96px;place-items:center';
        for (const size of [14,20,32,68,82]) for (const compound of 'HMSIW') {
            const badge = template.cloneNode(true);
            badge.dataset.compound = compound;
            badge.querySelector('.tyre-glyph').textContent = compound;
            badge.style.setProperty('--tyre-size',size+'px');
            board.append(badge);
        }
        document.body.append(board);
    }""")
    board = page.locator("#ink-test")
    def capture():
        return base64.b64encode(board.screenshot()).decode("ascii")
    painted = capture()
    page.add_style_tag(content="#ink-test .tyre-glyph {visibility:hidden}")
    return page.evaluate("""async ([painted, blank]) => {
        async function pixels(png) {
            const img = new Image();
            img.src = 'data:image/png;base64,'+png;
            await img.decode();
            const canvas = document.createElement('canvas');
            canvas.width = img.width; canvas.height = img.height;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img,0,0);
            return ctx.getImageData(0,0,img.width,img.height);
        }
        const [full,ring] = await Promise.all([painted,blank].map(pixels));
        const pitch = full.width/5, scale = pitch/96;
        const result = [];
        for (let row=0;row<5;row++) for(let col=0;col<5;col++) {
            let weight=0,sx=0,sy=0;
            let xmin=pitch,xmax=-1,ymin=pitch,ymax=-1;
            let left=pitch,right=-1,top=pitch,bottom=-1;
            for(let y=0;y<pitch;y++) for(let x=0;x<pitch;x++) {
                const idx=4*((row*pitch+y)*full.width+col*pitch+x);
                if ([17,18,22].some((bg,c)=>ring.data[idx+c]-bg>=16)) {
                    left=Math.min(left,x);right=Math.max(right,x);
                    top=Math.min(top,y);bottom=Math.max(bottom,y);
                }
                const ink=Math.max(...[0,1,2].map(c=>full.data[idx+c]-ring.data[idx+c]));
                if (ink<16) continue;
                weight+=ink;sx+=ink*(x+.5);sy+=ink*(y+.5);
                xmin=Math.min(xmin,x);xmax=Math.max(xmax,x);
                ymin=Math.min(ymin,y);ymax=Math.max(ymax,y);
            }
            if (!weight) throw Error('Missing ink');
            const cx=(left+right+1)/2, cy=(top+bottom+1)/2;
            const offset=(v,center)=>Math.round((v-center)/scale*100)/100;
            result.push({code:'HMSIW'[col],size:[14,20,32,68,82][row],
                x:offset((xmin+xmax+1)/2,cx),y:offset((ymin+ymax+1)/2,cy),
                massX:offset(sx/weight,cx),massY:offset(sy/weight,cy)});
        }
        return result;
    }""",[painted,capture()])


if __name__ == "__main__":
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome")
        for scale in (1,1.5,2):
            page = browser.new_page(device_scale_factor=scale)
            page.goto((sys.argv[1] if len(sys.argv)>1 else "http://127.0.0.1:8765")+"?source=demo")
            result = measure(page)
            for row in result:
                assert max(abs(row[k]) for k in ("x","y")) <= .5, (scale,row)
                assert max(abs(row[k]) for k in ("massX","massY")) <= .8, (scale,row)
            print(f"DPR {scale}: {len(result)} samples passed; "
                  f"max edge offset {max(abs(r[k]) for r in result for k in ('x','y')):.2f} CSS px, "
                  f"max ink offset {max(abs(r[k]) for r in result for k in ('massX','massY')):.2f} CSS px")
            page.close()
