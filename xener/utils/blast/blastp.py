import sys
import time
import subprocess
from typing import Literal
from pathlib import Path
import os

import pandas as pd

from ..logger import logger

cmd_blastp_base = "blastp -query {query_fasta} -db {db_path} -out {output_file} " +\
                    "{other_args} -task blastp-fast -outfmt 6 " +\
                    "-mt_mode 1 -num_threads {num_threads} "

# Use explicit -outfmt column spec to guarantee column order across BLAST+ versions.
_BLAST_OUTFMT = (
    "6 qseqid sseqid pident length mismatch gapopen "
    "qstart qend sstart send evalue bitscore"
)
_BLAST_COLUMNS = [
    "qseqid", "sseqid", "pident", "length", "mismatch", "gapopen",
    "qstart", "qend", "sstart", "send", "evalue", "bitscore",
]


def _resolve_blastp_exe(blastp_exe):
    """Validate and resolve a user-supplied blastp executable.

    Args:
        blastp_exe: ``None`` (use system ``blastp``), a path to an executable
            file (``/opt/conda/envs/x/bin/blastp``), or a directory in which
            to find ``blastp`` (``/opt/conda/envs/x/bin``). Empty string is
            treated as ``None``.

    Returns:
        The resolved absolute path to the blastp executable as a string.

    Raises:
        RuntimeError: when ``blastp_exe`` is set but the executable is missing
            or not runnable. A missing executable would silently fall back to
            the system PATH otherwise, defeating the purpose of pinning it.
    """
    if blastp_exe is None or blastp_exe == '':
        return 'blastp'
    exe = Path(blastp_exe).expanduser()
    if exe.is_dir():
        exe = exe / 'blastp'
    if not exe.exists():
        raise RuntimeError(
            f'blastp executable not found at {exe}. '
            f'Pass blastp_path as an executable file (e.g. /opt/conda/bin/blastp) '
            f'or as the directory containing blastp; omit it to use the system PATH.'
        )
    if not os.access(str(exe), os.X_OK):
        raise RuntimeError(
            f'blastp executable at {exe} exists but is not executable. '
            f'Check file permissions.'
        )
    return str(exe)


def blastp(query_fasta:Path, db_path:Path, output_file:Path, num_threads:int=None,
           blastp_exe=None, **kwargs) -> pd.DataFrame:
    """
    Execute BLASTP alignment.

    Args:
        query_fasta: Query fasta file path.
        db_path: BLAST database path.
        output_file: BLASTP result output file path.
        num_threads: Number of threads; if None, automatically set.
        blastp_exe: Path to the blastp executable. Accepts ``None`` (use
            ``blastp`` from PATH), a path to the executable itself, or a
            directory containing ``blastp`` (e.g. a conda env's ``bin/``).
        kwargs: Additional BLASTP parameters, default evalue=1e-5.

    Returns:
        Processed BLASTP result DataFrame.
    """
    tmp_output_file = output_file.with_suffix('.csv')
    if not os.path.exists(output_file):
        if num_threads is None:
            cpu_count = os.cpu_count()
            if cpu_count is None:
                num_threads = 1
            else:
                num_threads = max(1, int(cpu_count * 0.7))
        kwargs.setdefault('evalue', 1e-5)
        resolved_exe = _resolve_blastp_exe(blastp_exe)
        cmd = [
            resolved_exe,
            "-query", str(query_fasta),
            "-db", str(db_path),
            "-out", str(tmp_output_file),
            "-task", "blastp-fast",
            "-outfmt", _BLAST_OUTFMT,
            "-mt_mode", "1",
            "-num_threads", str(num_threads),
        ]
        for k, v in kwargs.items():
            cmd.extend([f"-{k}", str(v)])
        logger.info('BLASTP starting: query=%s, db=%s, threads=%s, exe=%s',
                    query_fasta, db_path, num_threads, resolved_exe)
        logger.debug('BLASTP command: %s', ' '.join(cmd))
        t0 = time.time()
        result = subprocess.run(cmd, stderr=subprocess.PIPE)
        elapsed = time.time() - t0
        if result.returncode != 0:
            logger.error('BLASTP failed with returncode=%s after %.2fs: %s',
                         result.returncode, elapsed,
                         result.stderr.decode(errors='replace') if result.stderr else '(no stderr)')
            raise RuntimeError(f'BLASTP failed (returncode={result.returncode})')
        if result.stderr:
            logger.warning('BLASTP stderr (returncode=0, %.2fs): %s', elapsed, result.stderr.decode(errors='replace'))
        if os.path.exists(tmp_output_file):
            with open(tmp_output_file) as f:
                n_hits = max(0, sum(1 for _ in f) - 1)
        else:
            n_hits = 0
        logger.info('BLASTP done in %.2fs: %s hits in %s', elapsed, n_hits, tmp_output_file)
        blast_result = pd.read_csv(tmp_output_file, sep='\t', header=None)
        blast_result.columns = _BLAST_COLUMNS
        blast_result = blast_result.loc[blast_result.groupby(['qseqid', 'sseqid'])['bitscore'].idxmax()]
        logger.info('BLASTP best-hits per (qseqid,sseqid): %s rows', len(blast_result))
        os.remove(tmp_output_file)
        blast_result.to_csv(output_file, index=False)
    else:
        blast_result = pd.read_csv(output_file)
        logger.info('BLASTP cache hit: %s (%s rows, skipping alignment)', output_file, len(blast_result))

    return blast_result

if __name__ == '__main__':
    res = blastp(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    logger.info(f'BLASTP result: {res}')
