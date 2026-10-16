import statistics

def select(rows, parameters):
    start = parameters['offset']
    end = start + parameters['page_size']
    return rows[start:end], {'reason': 'pagination', 'boundary_index': min(end, len(rows)), 'offset': start}
