
def fmt_django(table_name, table_module):
    return table_name

def fmt_underscore(table_name, table_module):
    module_parts = table_module.split('.')
    models_index = module_parts.index('models')

    # the schema name is always in front of the word 'models'
    schema = module_parts[models_index-1]

    # prefix 'monolith' to the front of the schema and suffix with the table name
    # also remove all periods and lowercase the string
    return '_'.join([schema, table_name]).replace('.', '_').lower()


fmt_choices_map = {
    "underscore": fmt_underscore,
    "django": fmt_django
}

fmt_choices = list(fmt_choices_map.keys())

def format_table(formatter, table_name, table_module):
    return fmt_choices_map[formatter](table_name, table_module)