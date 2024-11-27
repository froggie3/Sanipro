import argparse
import logging
import pprint
from collections.abc import Sequence

from sanipro import common
from sanipro.filters.exclude import ExcludeCommand
from sanipro.filters.fuzzysort import SimilarCommand
from sanipro.filters.mask import MaskCommand
from sanipro.filters.random import RandomCommand
from sanipro.filters.reset import ResetCommand
from sanipro.filters.roundup import RoundUpCommand
from sanipro.filters.sort import SortCommand
from sanipro.filters.sort_all import SortAllCommand
from sanipro.filters.unique import UniqueCommand
from sanipro.utils import HasPrettyRepr

from . import color
from .help_formatter import SaniproHelpFormatter
from .utils import get_debug_fp, get_log_level_from

logger_root = logging.getLogger()

logger = logging.getLogger(__name__)


class Commands(HasPrettyRepr):
    # features usable in parser_v1
    mask: Sequence[str]
    random = False
    sort = False
    sort_all = False
    similar = False
    unique = False

    # basic functions
    exclude: Sequence[str]
    input_delimiter = ","
    interactive = False
    output_delimiter = ", "
    roundup = 2
    ps1 = f"\001{color.default}\002>>>\001{color.RESET}\002 "

    replace_to = ""
    filter: str | None = None
    use_parser_v2 = False
    verbose: int | None = None

    # subcommands options
    reverse = False

    seed: int | None = None

    value: float | None = None

    similar_method = None
    sort_all_method = None

    kruskal = None
    prim = None

    command_classes = (
        ExcludeCommand,
        MaskCommand,
        RandomCommand,
        ResetCommand,
        RoundUpCommand,
        SimilarCommand,
        SortAllCommand,
        SortCommand,
        UniqueCommand,
    )

    def get_logger_level(self) -> int:
        if self.verbose is None:
            return logging.WARNING
        try:
            log_level = get_log_level_from(self.verbose)
            return log_level
        except ValueError:
            raise ValueError("the maximum two -v flags can only be added")

    def debug(self) -> None:
        pprint.pprint(self, get_debug_fp())

    @classmethod
    def prepare_parser(cls) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="sanipro",
            description=(
                "Toolbox for Stable Diffusion prompts. "
                "'Sanipro' stands for 'pro'mpt 'sani'tizer."
            ),
            formatter_class=SaniproHelpFormatter,
            epilog="Help for each filter is available, respectively.",
        )

        parser.add_argument(
            "-v",
            "--verbose",
            action="count",
            help=(
                "Switch to display the extra logs for nerds, "
                "This may be useful for debugging. Adding more flags causes your terminal more messier."
            ),
        )

        parser.add_argument(
            "-d",
            "--input-delimiter",
            type=str,
            default=cls.input_delimiter,
            help=("Preferred delimiter string for the original prompts. " ""),
        )

        parser.add_argument(
            "-s",
            "--output-delimiter",
            default=cls.output_delimiter,
            type=str,
            help=("Preferred delimiter string for the processed prompts. " ""),
        )

        parser.add_argument(
            "-p",
            "--ps1",
            default=cls.ps1,
            type=str,
            help=(
                "The custom string that is used to wait for the user input "
                "of the prompts."
            ),
        )

        parser.add_argument(
            "-i",
            "--interactive",
            default=cls.interactive,
            action="store_true",
            help=(
                "Provides the REPL interface to play with prompts. "
                "The program behaves like the Python interpreter."
            ),
        )

        parser.add_argument(
            "-u",
            "--roundup",
            default=cls.roundup,
            type=int,
            help=(
                "All the token with weights (x > 1.0 or x < 1.0) "
                "will be rounded up to n digit(s)."
            ),
        )

        parser.add_argument(
            "-x",
            "--exclude",
            type=str,
            nargs="*",
            help=(
                "Exclude this token from the original prompt. "
                "Multiple options can be specified."
            ),
        )

        parser.add_argument(
            "--use-parser-v2",
            "-2",
            action="store_true",
            help=(
                "Switch to use another version of the parser instead. "
                "This might be inferrior to the default parser "
                "as it only parses the prompt and does nothing at all."
            ),
        )

        subparser = parser.add_subparsers(
            title="filter",
            description=(
                "List of available filters that can be applied to the prompt. "
                "Just one filter can be applied at once."
            ),
            dest="filter",
            metavar="FILTER",
        )

        for cmd in cls.command_classes:
            cmd.inject_subparser(subparser)

        return parser

    @property
    def get_delimiter(self) -> common.Delimiter:
        return common.Delimiter(self.input_delimiter, self.output_delimiter)

    def get_pipeline_from(self, use_parser_v2: bool) -> common.PromptPipeline:
        delim = self.get_delimiter
        if not use_parser_v2:
            return delim.create_pipeline(common.PromptPipelineV1)
        return delim.create_pipeline(common.PromptPipelineV2)

    def get_pipeline(self) -> common.PromptPipeline:
        command_ids = [cmd.command_id for cmd in self.command_classes]
        command_funcs = (
            lambda: ExcludeCommand(self.exclude),
            lambda: MaskCommand(self.mask, self.replace_to),
            lambda: RandomCommand(self.seed),
            lambda: ResetCommand(self.value),
            lambda: SimilarCommand.create_from_cmd(cmd=self, reverse=self.reverse),
            lambda: SortAllCommand.create_from_cmd(cmd=self, reverse=self.reverse),
            lambda: SortCommand(self.reverse),
            lambda: UniqueCommand(self.reverse),
        )
        command_map = dict(zip(command_ids, command_funcs))

        if self.use_parser_v2:
            if self.filter in command_ids:
                raise NotImplementedError(
                    f"the '{self.filter}' command is not available "
                    "when using parse_v2."
                )

            logger.warning("using parser_v2.")

        pipeline = self.get_pipeline_from(self.use_parser_v2)
        # always round
        pipeline.append_command(RoundUpCommand(self.roundup))

        if self.filter is not None:
            lambd = command_map[self.filter]
            pipeline.append_command(lambd())

        return pipeline

    @classmethod
    def from_sys_argv(cls, arg_val: Sequence) -> "Commands":
        parser = cls.prepare_parser()
        args = parser.parse_args(arg_val, namespace=cls())

        return args
