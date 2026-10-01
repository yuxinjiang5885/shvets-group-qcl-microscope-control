"""Read-only orientation identity evidence; no normalization or hardware access."""
import sys


def orientation_diagnostics(value, expected, *, run_id, phase):
    actual_class, expected_class = type(value), type(expected)
    def class_info(cls):
        module = sys.modules.get(cls.__module__)
        return dict(type=repr(cls), qualname=cls.__qualname__, module=cls.__module__, class_id=id(cls),
                    module_id=id(module) if module is not None else None,
                    module_file=getattr(module, '__file__', None))
    return dict(run_id=run_id, phase=phase, received_repr=repr(value), received_str=str(value),
                raw_value=getattr(value, 'value', value),
                received_value=repr(getattr(value, 'value', value)),
                actual=class_info(actual_class), expected=class_info(expected_class),
                expected_repr=repr(expected), equal=value == expected,
                identical=value is expected,
                orientation_modules=[dict(name=name, module_id=id(module),
                    file=getattr(module, '__file__', None),
                    class_id=id(vars(module)['Orientation']))
                    for name, module in list(sys.modules.items())
                    if module is not None and isinstance(vars(module).get('Orientation'), type)
                    and vars(module)['Orientation'].__name__ == 'Orientation'])
