#
# Tcl package index file
#
# On Tk 9.0 and higher, do a no-op load, as svg support is buildin.
# As Tk may be loaded as a package, do the test on package require.
# Note, that multiple Tk packages with different versions may be available.
# The right Tk should be loaded before package require tksvg anyway.

package ifneeded tksvg 0.16 \
	"if {\[package vcompare 9.0a0 \[package require Tk\]\] == 1} {
		[list load [file join $dir tksvg016t.dll] [string totitle tksvg]]
	} else {
		package provide tksvg 0.16
	}"
