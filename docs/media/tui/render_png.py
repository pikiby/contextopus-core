import ctypes as c,re
from pathlib import Path
r=c.CDLL('librsvg-2.so.2'); ca=c.CDLL('libcairo.so.2')
r.rsvg_handle_new_from_file.argtypes=[c.c_char_p,c.c_void_p];r.rsvg_handle_new_from_file.restype=c.c_void_p
r.rsvg_handle_render_cairo.argtypes=[c.c_void_p,c.c_void_p]
ca.cairo_image_surface_create.argtypes=[c.c_int,c.c_int,c.c_int];ca.cairo_image_surface_create.restype=c.c_void_p
ca.cairo_create.argtypes=[c.c_void_p];ca.cairo_create.restype=c.c_void_p
ca.cairo_surface_write_to_png.argtypes=[c.c_void_p,c.c_char_p]
for p in Path('docs/media/tui').glob('*.svg'):
 s=p.read_text();w,h=map(float,re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"',s).groups())
 surf=ca.cairo_image_surface_create(0,int(w),int(h));ctx=ca.cairo_create(surf)
 fixed=p.with_suffix('.render.svg');fixed.write_text(s.replace('<svg ', '<svg xml:space="preserve" ',1));handle=r.rsvg_handle_new_from_file(str(fixed).encode(),None);fixed.unlink();r.rsvg_handle_render_cairo(handle,ctx)
 ca.cairo_surface_write_to_png(surf,str(p.with_suffix('.png')).encode())
from PIL import Image
frames=[Image.open('docs/media/tui/'+name+'-wide.png').convert('RGB') for name in ('main','settings','preview')]
size=(max(f.width for f in frames),max(f.height for f in frames))
padded=[]
for f in frames:
 canvas=Image.new('RGB',size,'#111111');canvas.paste(f,(0,0));padded.append(canvas)
padded[0].save('docs/media/tui/settings-demo.gif',save_all=True,append_images=padded[1:],duration=1400,loop=0,disposal=2)
