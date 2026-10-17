"""Apply relevance to the full pool, then cap the requested result units."""


def select(rows, parameters):
    relevant = [row for row in rows if row['distance'] <= parameters['d_max']]
    chosen = relevant[:parameters['N']]
    omitted = len(relevant) - len(chosen)
    relevance = {'reason': 'distance_threshold' if len(relevant) < len(rows) else 'no_cut',
                 'retained': len(relevant), 'threshold_removed': len(rows) - len(relevant)}
    return chosen, {'reason': 'result_cap' if omitted else relevance['reason'],
                    'boundary_index': len(chosen), 'relevance': relevance,
                    'result_cap': {'limit': parameters['N'], 'omitted': omitted}}
