"""Optional tiger disambiguation using agreement of two CUDA image views.

Never consults the requested recipe. Keeps the original 16-class detector output
for auditing. A ram prediction alone cannot become a supported seal.
"""
from .gpu import choose_evidence


def agreed_tiger(original, mirrored, context, score=.85, margin=.15):
    base = choose_evidence(original)
    if not original or original[0]['source_label'] != 'Hitsuji(Ram)' or base['score'] < .5:
        return base, False
    views = [choose_evidence(v) for v in (mirrored, context)]
    if not all(v['sign'] == 'tiger' and v['score'] >= score and v['margin'] >= margin for v in views):
        return base, False
    return {'sign':'tiger', 'score':min(v['score'] for v in views),
            'margin':min(v['margin'] for v in views)}, True


def refine_tiger(model, image, detections, minimum_score=.85):
    base = choose_evidence(detections)
    if not detections or detections[0]['source_label'] != 'Hitsuji(Ram)' or base['score'] < .5:
        return base, None
    cp = model.cp
    x1,y1,x2,y2 = detections[0]['box']
    cx,cy = (x1+x2)/2,(y1+y2)/2
    side = max(x2-x1,y2-y1)*3.5
    h,w = image.shape[:2]
    left,top = max(0,int(cx-side/2)), max(0,int(cy-side/2))
    right,bottom = min(w,int(cx+side/2)), min(h,int(cy+side/2))
    if right-left<32 or bottom-top<32:
        return base, None
    mirrored = cp.ascontiguousarray(image[:,::-1])
    context = cp.ascontiguousarray(image[top:bottom,left:right])
    cp.cuda.get_current_stream().synchronize()
    mirror_d = model.infer(mirrored)
    context_d = model.infer(context)
    evidence, accepted = agreed_tiger(detections,mirror_d,context_d,score=minimum_score)
    return evidence, {'method':'mirror_and_context_agreement','accepted':accepted,
                      'context_box':[left,top,right,bottom], 'mirror_detections':mirror_d,
                      'context_detections':context_d, 'minimum_score':minimum_score}
