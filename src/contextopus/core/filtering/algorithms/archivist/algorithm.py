"""Archivist procedure over the requested units, grouped by the caller."""
import statistics


def select(rows, parameters):
    kept = [row for row in rows if parameters['d_max'] is None or row['distance'] <= parameters['d_max']]
    boundary = {'reason':'distance_threshold' if len(kept) < len(rows) else 'no_cut',
                'boundary_index':len(kept), 'threshold_removed':len(rows) - len(kept)}
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
    relevance = {**boundary, 'retained':len(kept)}
    omitted = max(0, len(kept) - parameters['top_k'])
    kept = kept[:parameters['top_k']]
    boundary.update(reason='result_cap' if omitted else boundary['reason'],
                    boundary_index=len(kept), relevance=relevance,
                    result_cap={'limit':parameters['top_k'], 'omitted':omitted})
    return kept,boundary
