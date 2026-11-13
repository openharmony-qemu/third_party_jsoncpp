#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2023 Huawei Device Co., Ltd.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile

ARCHIVE = "jsoncpp-1.9.6.tar.gz"
TREE = "jsoncpp-1.9.6"
ARCHIVE_SHA256 = "f93b6dd7ce796b13d02c108bc9f79812245a82e577581c4c9aabe57075c90ea2"
OUTPUTS = ("src/lib_json/json_reader.cpp", "src/lib_json/json_value.cpp",
           "src/lib_json/json_writer.cpp", "include/json/json.h")


def real_directory(path):
    path = Path(os.path.abspath(path))
    if path == Path(path.anchor):
        raise ValueError("filesystem root is not a generation directory")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError("generation path must not contain symlinks: " + str(part))
    if path.exists() and not path.is_dir():
        raise ValueError("generation path is not a directory: " + str(path))
    return path


def validate_archive(source):
    archive = source / ARCHIVE
    if archive.is_symlink() or not archive.is_file():
        raise ValueError("jsoncpp archive must be a real file")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("unknown jsoncpp 1.9.6 archive")
    with tarfile.open(archive, "r:gz") as compressed:
        for member in compressed.getmembers():
            path = PurePosixPath(member.name)
            if (path.is_absolute() or ".." in path.parts or not path.parts
                    or path.parts[0] != TREE or not (member.isfile() or member.isdir())):
                raise ValueError("unsafe jsoncpp archive member: " + member.name)
    return archive


def verify_tree(tree):
    if tree.is_symlink() or not tree.is_dir():
        raise ValueError("jsoncpp generated tree must be a real directory")
    for entry in tree.rglob("*"):
        if entry.is_symlink() or not (entry.is_file() or entry.is_dir()):
            raise ValueError("unsafe jsoncpp generated entry: " + str(entry))
    for relative in OUTPUTS:
        entry = tree / relative
        if not entry.is_file() or entry.stat().st_size == 0:
            raise ValueError("missing jsoncpp generated output: " + relative)


def empty_gn_skeleton(tree):
    # GN may create source-output parent directories before this action.
    # Only an entirely directory-only, known-output skeleton is incomplete
    # generation, never a nonempty/partial/unsafe previous generated tree.
    if tree.is_symlink() or not tree.is_dir():
        return False
    allowed = {str(parent) for name in OUTPUTS
               for parent in PurePosixPath(name).parents if str(parent) != "."}
    for entry in tree.rglob("*"):
        if (entry.is_symlink() or not entry.is_dir()
                or str(entry.relative_to(tree)) not in allowed):
            return False
    return True


def install(source, generated):
    source = Path(source).resolve()
    archive = validate_archive(source)
    generated = real_directory(generated)
    if source == generated or source in generated.parents:
        raise ValueError("jsoncpp generation must not write into source")
    generated.mkdir(parents=True, exist_ok=True)
    destination = generated / TREE
    if (destination.exists() or destination.is_symlink()) and not empty_gn_skeleton(destination):
        verify_tree(destination)
    # GN consumes only generated sources and headers. A unique staging tree
    # avoids source writes and cross-product extraction/removal races.
    with tempfile.TemporaryDirectory(prefix=".jsoncpp-install-", dir=generated) as temporary:
        stage = Path(temporary)
        subprocess.run(["tar", "-xzf", str(archive), "-C", str(stage), "--no-same-owner"], check=True)
        extracted = stage / TREE
        verify_tree(extracted)
        previous = stage / "previous-generated-tree"
        had_previous = destination.exists()
        if had_previous:
            destination.rename(previous)
        try:
            extracted.rename(destination)
        except OSError:
            if had_previous:
                previous.rename(destination)
            raise
    print("verified jsoncpp 1.9.6 generated sources: " + str(destination))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gen-dir", required=True)
    parser.add_argument("--source-file", required=True)
    args = parser.parse_args()
    install(args.source_file, args.gen_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
