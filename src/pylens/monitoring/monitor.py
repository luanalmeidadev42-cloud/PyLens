"""Process-tree resource sampling using psutil."""

from dataclasses import dataclass
from typing import Optional

import psutil


@dataclass(frozen=True)
class ProcessSample:
    cpu_percent: Optional[float]
    memory_rss_bytes: Optional[int]
    memory_vms_bytes: Optional[int]
    child_memory_rss_bytes: Optional[int]
    thread_count: Optional[int]
    process_count: Optional[int]
    process_tree_complete: bool


class ProcessMonitor:
    def __init__(self, pid: int) -> None:
        """### O que faz
        Prepara o monitor para acompanhar o processo identificado por `pid`.
        """
        self.root = psutil.Process(pid)
        self.process_cache = {pid: self.root}
        try:
            self.root.cpu_percent(interval=None)
        except psutil.Error:
            pass

    def sample(self) -> ProcessSample:
        """### O que faz
        Mede CPU, memória, threads e processos da árvore observada.

        Se não for possível observar a árvore inteira, marca a amostra incompleta.
        """
        try:
            children = self.root.children(recursive=True)
        except psutil.NoSuchProcess:
            return ProcessSample(None, None, None, None, None, None, False)
        except psutil.Error:
            children = []
            tree_complete = False
        else:
            tree_complete = True

        processes = [self.root]
        previous_cache = self.process_cache
        current_cache = {self.root.pid: self.root}
        for child in children:
            try:
                cached = previous_cache.get(child.pid)
                if cached is None or cached.create_time() != child.create_time():
                    cached = child
                    cached.cpu_percent(interval=None)
                processes.append(cached)
                current_cache[cached.pid] = cached
            except psutil.Error:
                tree_complete = False
                continue
        self.process_cache = current_cache

        cpu_total = 0.0
        rss_total = 0
        vms_total = 0
        child_rss_total = 0
        threads_total = 0
        valid_processes = 0
        valid_cpu = 0
        valid_memory = 0
        valid_threads = 0

        for index, process in enumerate(processes):
            try:
                cpu_total += process.cpu_percent(interval=None)
                valid_cpu += 1
                memory = process.memory_info()
                rss_total += memory.rss
                vms_total += memory.vms
                if index > 0:
                    child_rss_total += memory.rss
                valid_memory += 1
                threads_total += process.num_threads()
                valid_threads += 1
                valid_processes += 1
            except psutil.Error:
                tree_complete = False
                continue

        if not tree_complete:
            return ProcessSample(None, None, None, None, None, None, False)

        return ProcessSample(
            cpu_percent=cpu_total if valid_cpu else None,
            memory_rss_bytes=rss_total if valid_memory else None,
            memory_vms_bytes=vms_total if valid_memory else None,
            child_memory_rss_bytes=child_rss_total if valid_memory else None,
            thread_count=threads_total if valid_threads else None,
            process_count=valid_processes if valid_processes else None,
            process_tree_complete=True,
        )
