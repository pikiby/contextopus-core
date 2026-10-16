"""Archivist procedure with document-key grouping before relevance cuts."""
import json
import statistics


def select(rows, parameters):
    unique = {}
    for row in rows:
        identity = json.dumps(row.get('key',row.get('id',row.get('object_id',row.get('material_id')))),sort_keys=True)
        unique.setdefault(identity,row)
    kept = [row for row in unique.values() if parameters['d_max'] is None or row['distance'] <= parameters['d_max']]
    boundary = {'reason':'distance_threshold' if len(kept) < len(unique) else 'no_cut','boundary_index':len(kept),'grouping':'document_key_before_cut'}
    if len(kept) > 2:
        gaps = [b['distance'] - a['distance'] for a,b in zip(kept,kept[1:])]
        positive = sorted(gap for gap in gaps if gap > 0)
        if positive:
            upper_median = positive[len(positive)//2]
            threshold = max(.02,upper_median * 3)
            boundary.update(upper_median_positive_gap=upper_median,jump_threshold=threshold)
            for index,gap in enumerate(gaps):
                if gap >= threshold:
                    kept = kept[:index+1]
                    boundary.update(reason='distance_jump',boundary_index=index+1)
                    break
    if len(kept) > 3:
        head = statistics.median(row['distance'] for row in kept[:3])
        gaps = [b['distance'] - a['distance'] for a,b in zip(kept,kept[1:])]
        positive = [gap for gap in gaps if gap > 0]
        delta = max(.02, statistics.median(positive)*2) if positive else .02
        boundary.update(head=head,plateau_distance_delta=delta,plateau_local_gap=.01)
        for index in range(2,len(kept)):
            if kept[index]['distance'] > head + delta and gaps[index-1] < .01:
                kept = kept[:index]
                boundary.update(reason='archivist_weak_plateau',boundary_index=index)
                break
    if len(kept) > parameters['top_k']:
        kept = kept[:parameters['top_k']]
        boundary.update(reason='top_k',boundary_index=len(kept))
    return kept,boundary
