import statistics

def select(rows, parameters):
    kept = [r for r in rows[:parameters['N']] if r['distance'] <= parameters['d_max']]
    return kept, {'reason': 'distance_threshold' if len(kept) < min(len(rows), parameters['N']) else 'nearest_n', 'boundary_index': len(kept)}
