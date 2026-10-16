import statistics

def select(rows, parameters):
    return rows[:parameters['N']], {'reason': 'nearest_n', 'boundary_index': min(len(rows), parameters['N'])}
