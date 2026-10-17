"""Nearest requested units, without a relevance estimate."""


def select(rows, parameters):
    chosen = rows[:parameters['N']]
    omitted = len(rows) - len(chosen)
    return chosen, {'reason': 'result_cap' if omitted else 'nearest_n',
                    'boundary_index': len(chosen),
                    'relevance': {'reason': 'not_evaluated', 'retained': len(rows)},
                    'result_cap': {'limit': parameters['N'], 'omitted': omitted}}
