from django_dbml.utils import to_snake_case
from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import models
from .formatter import fmt_choices, format_table


class Command(BaseCommand):
    help = "Generate a DBML file based on Django models"
    output_lines = []

    def add_arguments(self, parser):
        parser.add_argument(
            'args', metavar='app_label[.ModelName]', nargs='*',
            help='Restricts dbml generation to the specified app_label or app_label.ModelName.',
        )
        parser.add_argument(
            '--file', help="File to output the DBML to"
        )
        parser.add_argument(
            '--table-format', help="Formatter to use for the table name", choices=fmt_choices, default="django"
        )
        parser.add_argument(
            '--table-prefix', help="Prefix to add to table names", default=""
        )
        parser.add_argument(
            '--db-name', help="Project Database Name", default="database"
        )
        parser.add_argument(
            '--db-type', help="Project Database Type", default="PostgreSQL"
        )
        parser.add_argument(
            '--db-note', help="Project Database Note", default=""
        )
        parser.add_argument(
            '--table-filter', help="Comma seperated list of table patterns to omit", default=""
        )

    def get_field_notes(self, field):
        if len(field.keys()) == 1:
            return ""

        attributes = []
        for name, value in field.items():
            if name == "type":
                continue

            if name == "note":
                attributes.append('note:"{}"'.format(value))
                continue

            if name in ("null", "pk", "unique"):
                attributes.append(name)
                continue

            attributes.append("{}:{}".format(name, value))
        if not attributes:
            return ""
        return "[{}]".format(", ".join(attributes))

    def get_app_tables(self, app_labels):
        # get the list of models to generate DBML for

        # if no apps are specified, process all models
        if not app_labels:
            return apps.get_models()

        # get specific models when app or app.model is specified
        app_tables = []
        for app in app_labels:
            app_label_parts = app.split('.')
            # first part is always the app label
            app_label = app_label_parts[0]
            # use the second part as model label if set
            model_label = app_label_parts[1] if len(app_label_parts) > 1 else None
            try:
                app_config = apps.get_app_config(app_label)
            except LookupError as e:
                raise CommandError(str(e))

            app_config = apps.get_app_config(app_label)
            if model_label:
                app_tables.append(app_config.get_model(model_label))
            else:
                app_tables.extend(app_config.get_models())

        return app_tables


    def addLine(self, line):
        self.output_lines.append(line)

    def outputDbml(self, output_file):
        output_string = "\n".join(self.output_lines)
        if output_file is None:
            print(output_string)
            print("\n")
        else:
            with open(output_file, "w") as output:
                output.write(output_string)
                output.write("\n")
            output.close()


    def handle(self, *app_labels, **kwargs):
        output_file = kwargs["file"]
        fmt = kwargs["table_format"]
        prefix = kwargs["table_prefix"]
        table_filter = list(filter(None, kwargs["table_filter"].split(',')))

        self.addLine(f"Project {kwargs['db_name']} {{")
        self.addLine(f"    database_type: '{kwargs['db_type']}'")
        self.addLine(f"    Note: \'\'\'")
        self.addLine(f"    {kwargs['db_note']}")
        self.addLine(f"    \'\'\'")
        self.addLine(f"}}")

        all_fields = {}
        allowed_types = ["ForeignKey", "ManyToManyField"]
        for field_type in models.__all__:
            if "Field" not in field_type and field_type not in allowed_types:
                continue

            all_fields[field_type] = to_snake_case(field_type.replace("Field", ""),)

        ignore_types = (
            models.fields.reverse_related.ManyToOneRel,
            models.fields.reverse_related.ManyToManyRel,
        )

        tables = {}
        app_tables = self.get_app_tables(app_labels)

        for app_table in app_tables:
            table_name = prefix + format_table(fmt, app_table.__name__, app_table.__module__)
            tables[table_name] = {"fields": {}, "relations": []}

            for field in app_table._meta.get_fields():
                if isinstance(field, ignore_types):
                    continue

                field_attributes = list(dir(field))

                # print(table_name, field, type(field))
                if isinstance(field, models.fields.related.OneToOneField):
                    tables[table_name]["relations"].append(
                        {
                            "type": "one_to_one",
                            "table_from": prefix + format_table(fmt, field.related_model.__name__, field.related_model.__module__),
                            "table_from_field": field.target_field.name,
                            "table_to": table_name,
                            "table_to_field": field.name,
                        }
                    )

                elif isinstance(field, models.fields.related.ForeignKey):
                    tables[table_name]["relations"].append(
                        {
                            "type": "one_to_many",
                            "table_from": prefix + format_table(fmt, field.related_model.__name__, field.related_model.__module__),
                            "table_from_field": field.target_field.name,
                            "table_to": table_name,
                            "table_to_field": field.name,
                        }
                    )

                elif isinstance(field, models.fields.related.ManyToManyField):
                    table_name_m2m = prefix + field.m2m_db_table()
                    # only define m2m table and relations on first encounter
                    if table_name_m2m not in tables.keys():
                        tables[table_name_m2m] = {"fields": {}, "relations": []}

                        tables[table_name_m2m]["relations"].append(
                            {
                                "type": "one_to_many",
                                "table_from": table_name_m2m,
                                "table_from_field": field.m2m_column_name(),
                                "table_to": prefix + format_table(fmt, field.model.__name__, field.model.__module__),
                                "table_to_field": field.m2m_target_field_name(),
                            }
                        )
                        tables[table_name_m2m]["relations"].append(
                            {
                                "type": "one_to_many",
                                "table_from": table_name_m2m,
                                "table_from_field": field.m2m_reverse_name(),
                                "table_to": prefix + format_table(fmt, field.related_model.__name__, field.related_model.__module__),
                                "table_to_field": field.m2m_target_field_name(),
                            }
                        )
                        tables[table_name_m2m]["fields"][field.m2m_reverse_name()] = {
                            "pk": True,
                            "type": "auto",
                        }

                        tables[table_name_m2m]["fields"][field.m2m_column_name()] = {
                            "pk": True,
                            "type": "auto",
                        }

                    continue

                tables[table_name]["fields"][field.name] = {
                    "type": all_fields.get(type(field).__name__),
                }

                if "help_text" in field_attributes and field.help_text:
                    help_text = field.help_text.replace('"', '\\"')
                    tables[table_name]["fields"][field.name]["note"] = help_text

                if "null" in field_attributes and field.null is True:
                    tables[table_name]["fields"][field.name]["null"] = True

                if "primary_key" in field_attributes and field.primary_key is True:
                    tables[table_name]["fields"][field.name]["pk"] = True

                if "unique" in field_attributes and field.unique is True:
                    tables[table_name]["fields"][field.name]["unique"] = True

                if app_table.__doc__:
                    tables[table_name]["note"] = app_table.__doc__

        for table_name, table in tables.items():
            if any(y in table_name for y in table_filter):
                print('SKIPPING: ', table_name, table_filter)
                continue

            self.addLine("\n")
            self.addLine("Table {} {{".format(table_name))
            for field_name, field in table["fields"].items():
                self.addLine(
                    "  {} {} {}".format(
                        field_name, field["type"], self.get_field_notes(field)
                    )
                )
            if 'note' in table:
                self.addLine("  Note: '''{}'''".format(table['note']))
            self.addLine("}")

            for relation in table["relations"]:
                if relation["type"] == "one_to_many":
                    self.addLine(
                        "ref: {}.{} > {}.{}".format(
                            relation["table_to"],
                            relation["table_to_field"],
                            relation["table_from"],
                            relation["table_from_field"],
                        )
                    )

                if relation["type"] == "one_to_one":
                    self.addLine(
                        "ref: {}.{} - {}.{}".format(
                            relation["table_to"],
                            relation["table_to_field"],
                            relation["table_from"],
                            relation["table_from_field"],
                        )
                    )
        
        self.outputDbml(output_file)


