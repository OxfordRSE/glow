#!/usr/bin/mawk -f

BEGIN {
  errorCount = 0;
}

{
  while (match($0, /\$\{[A-Z_][A-Z_0-9]*\}/) > 0) {
    k = substr($0, RSTART + 2, RLENGTH - 3);
    if (k in ENVIRON) {
      v = ENVIRON[k];
    } else {
      print "ERR: var not defined on line " NR ": ${" k "}" > "/dev/stderr";
      ++errorCount;
      v = "!!!VALUE-MISSING: " k "!!!"
    }
    gsub("\\$\\{" k "\\}", v);
  }
  print $0;
}

END {
  if (errorCount > 0) {
    print "" > "/dev/stderr";
    print errorCount " error(s) found." > "/dev/stderr";
    exit 1;
  }
}
