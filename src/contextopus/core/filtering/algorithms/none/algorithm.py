"""Page the requested units without a relevance estimate."""


def select(rows, parameters):
    start = parameters['offset']
    end = start + parameters['page_size']
    return rows[start:end], {
        'reason': 'pagination', 'boundary_index': min(end, len(rows)), 'offset': start,
        'relevance': {'reason': 'not_evaluated', 'retained': len(rows)},
        'result_cap': {'limit': parameters['page_size'], 'offset': start,
                       'omitted': max(0, len(rows) - end),
                       'next_offset': end if end < len(rows) else None},
    }
