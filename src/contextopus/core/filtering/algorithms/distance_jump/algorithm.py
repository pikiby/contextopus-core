import statistics

def select(rows, parameters):
    kept = [r for r in rows[:parameters['N']] if r['distance'] <= parameters['d_max']]
    boundary = {'reason': 'distance_threshold' if len(kept) < min(len(rows), parameters['N']) else 'no_jump', 'boundary_index': len(kept)}
    if len(kept) >= 3:
        gaps = [b['distance'] - a['distance'] for a,b in zip(kept, kept[1:])]
        positive = [gap for gap in gaps if gap > 0]
        if positive:
            threshold = max(parameters['min_jump'], statistics.median(positive) * parameters['multiplier'])
            boundary['jump_threshold'] = threshold
            for index,gap in enumerate(gaps):
                if gap >= threshold:
                    kept = kept[:index+1]
                    boundary.update(reason='distance_jump', boundary_index=index+1, gap=gap)
                    break
    return kept, boundary
