#!/bin/bash -eu

scmds=(
	# Test `stacks`
	"stacks"

	# Test `dmesg`
	"dmesg"

	# Test `lxlist`
	"addr modules | lxlist module list | member name"

	# Test `slabs` and `percpu`
	"slabs | filter \"obj.name == 'kmalloc-8'\" | member cpu_slab | percpu 0 1"

	# Test `pid`
	"pid 1"

	# Test `find_task`
	"find_task 1 2"

	# Test `threads`
	"threads"

	# Test `walk` and `slub_cache` walker
	"slabs | filter \"obj.name == 'TCP'\" | walk"

	# Test `rbtree` walker
	"addr vmap_area_root | rbtree vmap_area rb_node"

	# Test `fget`
	"find_task 1 | fget 1 4"
)

for ((i = 0; i < ${#scmds[@]}; i++)); do
	sudo /usr/local/bin/sdb -e "${scmds[$i]}"
done

zfs_scmds=(
	# Test `arc`
	"arc"

	# Test `zfs_dbgmsg`
	"zfs_dbgmsg"

	# Test `zio`
	"zio"

	# Test `spa`
	"spa -vmH"

	# Test `vdev` and `metaslab`
	"spa | vdev | metaslab"

	# Test `vdev` and `metaslab` and `range_tree`
	"spa | vdev | metaslab | head 1 | member ms_allocatable | range_tree"

	# Test `dbuf`
	"dbuf"

	# Test `dbuf` and `blkptr`
	"dbuf | head 1 | member db_blkptr | blkptr"

	# Test `spa` and `zhist`
	"spa | member spa_normal_class.mc_histogram | zhist"

	# Test `avl`
	"address spa_namespace_avl | avl"

	# Test `spl_kmem_caches`
	"spl_kmem_caches"
)

if $(lsmod | grep -q zfs); then
	echo "Detected ZFS kernel module... testing ZFS commands:"
	for ((i = 0; i < ${#zfs_scmds[@]}; i++)); do
		sudo /usr/local/bin/sdb -e "${zfs_scmds[$i]}"
	done
else
	echo "Can't find ZFS kernel module... skipping ZFS commands"
fi
