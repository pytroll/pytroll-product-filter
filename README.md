# pytroll-product-filter
Pytroll product filter

Take a (EUMETCast disseminated) satellite product file and send it on to a
configurable set of destinations if it covers a configurable area of
interest. Uses only the filename to determine the coverage, thus requiring at a
minimum the platform name and the start time (and preferably also the end time)
in the filename.