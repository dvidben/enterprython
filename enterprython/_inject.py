"""
enterprython - Type-based dependency-injection
"""

import configparser
import inspect
import sys
from typing import Any, Callable, Dict, Optional, Type, TypeVar, List, Generic

VER_3_7_AND_UP = sys.version_info[:3] >= (3, 7, 0)  # PEP 560

# pylint: disable=no-name-in-module
if VER_3_7_AND_UP:
    from typing import _GenericAlias  # type: ignore
else:
    pass
# pylint: enable=no-name-in-module

TypeT = TypeVar('TypeT')


class _Component(Generic[TypeT]):  # pylint: disable=unsubscriptable-object
    """Internal class to store components for DI."""

    def __init__(self, the_type: Callable[..., TypeT], singleton: bool) -> None:
        """Figure out and store base classes."""
        self._type = the_type
        self._is_singleton = singleton
        self._base_classes = inspect.getmro(the_type)  # type: ignore
        self._instance: Optional[TypeT] = None

    def matches(self, the_type: Callable[..., TypeT]) -> bool:
        """Check if component can be used for injection of the_type."""
        return the_type in self._base_classes

    def set_instance_if_singleton(self, instance: TypeT) -> None:
        """If this component is a singleton, set it's instance."""
        if self._is_singleton:
            assert self._instance is None
            self._instance = instance

    def get_instance(self) -> Optional[TypeT]:
        """Access singleton instance if present."""
        assert self._is_singleton or self._instance is None
        return self._instance

    def get_type(self) -> Callable[..., TypeT]:
        """Underlying target type of component."""
        return self._type


ENTERPRYTHON_CONFIG: Optional[configparser.ConfigParser] = None
ENTERPRYTHON_COMPONENTS: List[_Component] = []


def configure(config: configparser.ConfigParser) -> None:
    """Set global enterprython value configuration."""
    global ENTERPRYTHON_CONFIG  # pylint: disable=global-statement
    ENTERPRYTHON_CONFIG = config


def assemble(the_type: Callable[..., TypeT], **kwargs: Any) -> TypeT:
    """Create an instance of a certain type,
    using constructor injection if needed."""

    global ENTERPRYTHON_COMPONENTS  # pylint: disable=global-statement

    stored_component = _get_component(the_type)
    if stored_component:
        instance = stored_component.get_instance()
        if instance is not None:
            return instance  # type: ignore

    signature = inspect.signature(the_type)

    parameters: Dict[str, Type[Any]] = {}
    for param in signature.parameters.values():
        if param.name == 'self':
            continue
        if param.kind != inspect.Parameter.POSITIONAL_OR_KEYWORD:
            raise TypeError('Only parameters of kind POSITIONAL_OR_KEYWORD '
                            'supported in target functions.')
        parameters[param.name] = param.annotation

    arguments: Dict[str, Any] = kwargs
    for parameter_name, parameter_type in parameters.items():
        if _is_list_type(parameter_type):
            parameter_components = _get_components(_get_list_type_elem_type(parameter_type))
            arguments[parameter_name] = list(map(assemble,
                                                 map(lambda comp: comp.get_type(),
                                                     parameter_components)))
        else:
            parameter_component = _get_component(parameter_type)
            if parameter_component is not None:
                arguments[parameter_name] = assemble(parameter_component.get_type())
    result = the_type(**arguments)
    if stored_component:
        stored_component.set_instance_if_singleton(result)
    return result


def value(the_type: Callable[..., TypeT], config_section: str, value_name: str) -> TypeT:
    """Get a config value from the global enterprython config store."""
    assert the_type in [bool, float, int, str]
    if the_type == bool:
        return ENTERPRYTHON_CONFIG.getboolean(config_section, value_name)  # type: ignore
    if the_type == float:
        return ENTERPRYTHON_CONFIG.getfloat(config_section, value_name)  # type: ignore
    if the_type == int:
        return ENTERPRYTHON_CONFIG.getint(config_section, value_name)  # type: ignore
    return ENTERPRYTHON_CONFIG.get(config_section, value_name)  # type: ignore


def component(singleton: bool = True) -> Callable[[Callable[..., TypeT]],
                                                  Callable[..., TypeT]]:
    """Annotation to register a class to be available for DI to constructors."""

    def register(the_type: Callable[..., TypeT]) -> Callable[..., TypeT]:
        """Register component and forward type."""
        if not inspect.isclass(the_type):
            raise TypeError(f'Only classes can be registered.')
        if inspect.isabstract(the_type):
            raise TypeError(f'Can not register abstract class as component.')
        global ENTERPRYTHON_COMPONENTS  # pylint: disable=global-statement
        _add_component(the_type, singleton)
        return the_type

    return register


def _get_components(the_type: Callable[..., TypeT]) -> List[_Component]:
    """Return stored component for type if available."""
    return [stored_component
            for stored_component in ENTERPRYTHON_COMPONENTS
            if stored_component.matches(the_type)]


def _get_component(the_type: Callable[..., TypeT]) -> Optional[_Component]:
    """Return stored component for type if available."""
    components = _get_components(the_type)
    if len(components) > 1:
        raise TypeError(f'Ambiguous dependency {the_type.__name__}.')
    if not components:
        return None
    return components[0]


def _add_component(the_type: Callable[..., TypeT], singleton: bool) -> None:
    """Store new component for DI."""
    global ENTERPRYTHON_COMPONENTS  # pylint: disable=global-statement
    if _get_component(the_type) is not None:
        raise TypeError(f'{the_type.__name__} '
                        'already registered as component.')
    ENTERPRYTHON_COMPONENTS.append(_Component(the_type, singleton))


def _is_list_type(the_type: Callable[..., TypeT]) -> bool:
    try:
        if VER_3_7_AND_UP:
            return _is_instance(the_type,
                                _GenericAlias) and _type_origin_is(the_type, list)
        return issubclass(the_type, List)  # type: ignore
    except TypeError:
        return False


def _is_instance(the_value: TypeT, the_type: Callable[..., TypeT]) -> bool:
    return isinstance(the_value, the_type)  # type: ignore


def _type_origin_is(the_type: Callable[..., TypeT], origin: Any) -> bool:
    assert hasattr(the_type, '__origin__')
    return the_type.__origin__ is origin  # type: ignore


def _get_list_type_elem_type(list_type: Callable[..., TypeT]) -> Callable[..., Any]:
    """Return the type of a single element of the list type."""
    assert _is_list_type(list_type)
    list_args = list_type.__args__  # type: ignore
    assert len(list_args) == 1
    return list_args[0]  # type: ignore
