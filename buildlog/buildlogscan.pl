#!/usr/bin/perl
# Scan buildlog from binary builds, output src:, lib:, obj:
#open(BAR,"bom.csv") || die("can't open .csv");
#while (<BAR>)
#{
#	chomp;
#	($component,$version,$url,$license,$usage,$conflict,$ship,$percent,$search,$comment) = split(/,/);
#	next if ($conflict =~ /No Conflicts/);
#	print "$component,$license,$conflict\n";
#}
open(BAR,"sc.csv") || die("can't open .csv");
while (<BAR>)
{
	chomp;
	s/\"//g;
	($file,$component,$version,$license,$usage,$resolution,$discovery,$pct,$matched,$comment) = split(/,/);
	next if (!/Product1/);
	if ($file =~ m/\.(cpp|c|cxx|class|asp|js|jar|htm|xml)$/) {
		$file =~ s/.code.Product1.src//;
		$file =~ s/^\///;
		$srclist{$file} = $license;
	}
}
$verbose=0;
close(BAR);
while(<>)
{
    chomp;
    s/\"//g;
    s/\\/\//g;
    @args = split(/[ ,]/);
    $output = 0;
    map {
	if (/^i686-elf-/ || /ranlib/) {
		print "---------------------\n";
	}
	if (/-static/) {
	    print "static: ";
	}
	# Display JAVA/HTML files
	if ($output) {
	    print "out: $_\n";
	    $output = 0;
        }
	elsif (/\.(class|js|jar|asp|htm|xml)$/) {
	    print "cls: <$srclist{$_}> $_\n";
	}
	# Display C source files
	elsif (/\.(cpp|c|cxx)$/) {
	    print "src: <$srclist{$_}> $_\n";
	}
	# Display binary objects
	elsif (/\.(o|obj)$/) {
	    print "obj: $_\n";
	}
	elsif (/^-o$/) {
		$output = 1;
	}
	# Display -xxx options
	elsif (/^[^-]/ && $verbose) {
	    print "  other:$_\n";
	}
	# Display win32 libraries
	if (/.*\.lib$/) {
	    print "lib: $_\n";
	}
	# Display -lxxx libraries (libxxx.so)
	if (/^-[l]/) {
	    print "lib: $_\n";
	}
    } @args;
}

