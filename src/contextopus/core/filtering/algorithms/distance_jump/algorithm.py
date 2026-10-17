"""Evaluate the relevance boundary over all units before applying the result cap."""
import statistics


def select(rows, parameters):
    relevant = [row for row in rows if row['distance'] <= parameters['d_max']]
    threshold_removed = len(rows) - len(relevant)
    relevance = {'reason': 'distance_threshold' if threshold_removed else 'no_jump',
                 'threshold_removed': threshold_removed,
                 'jump_assessment': 'insufficient_candidates'}
    if len(relevant) >= 3:
        gaps = [b['distance'] - a['distance'] for a, b in zip(relevant, relevant[1:])]
        positive = [gap for gap in gaps if gap > 0]
        relevance['jump_assessment'] = 'no_positive_gaps' if not positive else 'no_jump'
        if positive:
            threshold = max(parameters['min_jump'], statistics.median(positive) * parameters['multiplier'])
            relevance['jump_threshold'] = threshold
            for index, gap in enumerate(gaps):
                if gap >= threshold:
                    relevant = relevant[:index + 1]
                    relevance.update(reason='distance_jump', jump_assessment='distance_jump',
                                     boundary_index=index + 1, gap=gap)
                    break
    if relevance['jump_assessment'] == 'insufficient_candidates' and not threshold_removed:
        relevance['reason'] = 'insufficient_candidates'
    relevance['retained'] = len(relevant)
    chosen = relevant[:parameters['N']]
    omitted = len(relevant) - len(chosen)
    return chosen, {
        **relevance, 'reason': 'result_cap' if omitted else relevance['reason'],
        'boundary_index': len(chosen), 'relevance': relevance,
        'result_cap': {'limit': parameters['N'], 'omitted': omitted},
    }
