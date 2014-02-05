import os
import tables

from collections import namedtuple, OrderedDict
from bisect import bisect_right

import gtrackcore.third_party.safeshelve as safeshelve

from gtrackcore.track.pytables.DatabaseHandler import BoundingRegionCreationDatabaseHandler
from gtrackcore.metadata.GenomeInfo import GenomeInfo
from gtrackcore.track.core.GenomeRegion import GenomeRegion
from gtrackcore.util.CustomExceptions import InvalidFormatError, OutsideBoundingRegionError, \
    BoundingRegionsNotAvailableError
from gtrackcore.util.CompBinManager import CompBinManager
from gtrackcore.util.CommonFunctions import getDirPath, createPath, getDatabaseFilename

BoundingRegionInfo = namedtuple('BoundingRegionInfo', \
                                ['start', 'end', 'startIdx', 'endIdx', 'startBinIdx', 'endBinIdx'])
BrInfoHolder = namedtuple('BrInfoHolder', ['brStarts', 'brInfos'])

BR_SHELVE_FILE_NAME = 'boundingRegions.shelve'

def isBoundingRegionFileName(fn):
    return fn == BR_SHELVE_FILE_NAME

class BoundingRegionContainer(object):
    def __init__(self, genome, track_name, allow_overlaps):
        assert allow_overlaps in [False, True]

        self._genome = genome
        self._track_name = track_name
        dir_path = getDirPath(track_name, genome, allowOverlaps=allow_overlaps)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
        self._fn = getDatabaseFilename(dir_path, track_name)

        self._contents = {} #None
        self._updated_chromosomes = set([])

        from gtrackcore.input.userbins.UserBinSource import MinimalBinSource
        minimal_bin_list = MinimalBinSource(genome)
        self._minimal_region = minimal_bin_list[0] if minimal_bin_list is not None else None

    def file_exists(self):
        return os.path.exists(self._fn)

    def store_bounding_regions(self, bounding_region_tuples, genome_element_chr_list, sparse):
        assert sparse in [False, True]

        temp_bounding_regions = self._create_bounding_regions_triples(bounding_region_tuples, genome_element_chr_list, sparse)

        table_description = self._create_table_description()
        db_handler = BoundingRegionCreationDatabaseHandler()
        db_handler.open()
        db_handler.create_table(table_description, len(bounding_region_tuples))

        row = db_handler.get_row()
        for br in temp_bounding_regions:
            row['seqid'] = br[0]
            row['start'] = br[1]
            row['end'] = br[2]
            row.append()

        db_handler.close()

    @staticmethod
    def _create_bounding_regions_triples(bounding_region_tuples, genome_element_chr_list, sparse):
        last_region = None
        temp_bounding_regions = []
        for br in bounding_region_tuples:
            if br.region < last_region:
                raise InvalidFormatError("Error: bounding regions in the same chromosome (sequence) are unsorted: %s > %s." % (last_region, br.region))
            if last_region.overlaps(br.region):
                raise InvalidFormatError("Error: bounding regions '%s' and '%s' overlap." % (last_region, br.region))
            if last_region.end == br.region.start:
                raise InvalidFormatError("Error: bounding regions '%s' and '%s' are adjoining (there is no gap between them)." % (last_region, br.region))
            if len(br.region) < 1:
                raise InvalidFormatError("Error: bounding region '%s' does not have positive length." % br.region)
            if not sparse and len(br.region) != br.elCount:
                raise InvalidFormatError("Error: track type representation is dense, but the length of bounding region '%s' is not equal to the element count: %s != %s" % (br.region, len(br.region), br.elCount))

            temp_bounding_regions.append((br.region.chr, br.region.start, br.region.end))

            last_region = br.region
        if sparse:
            diff = set(genome_element_chr_list) - set([br_triple[0] for br_triple in temp_bounding_regions])
            if len(diff) > 0:
                raise InvalidFormatError('Error: some chromosomes (sequences) contains data, but has no bounding regions: %s' % ', '.join(diff))

        return temp_bounding_regions

    @staticmethod
    def _create_table_description():
        return {
                'seqid': tables.StringCol(100),
                'start': tables.Int32Col(),
                'end': tables.Int32Col(),
               }

    def _update_contents_if_necessary(self, chr):
        #if self._contents is None:
        #    self._contents = {}
        #    if self.fileExists():
        #        self._contents.update(safeshelve.open(self._fn, 'r'))
        if not chr in self._updated_chromosomes:
            if self.file_exists():
                br_list_for_chr = safeshelve.open(self._fn, 'r').get(chr)
                if br_list_for_chr is not None:
                    self._contents[chr] = br_list_for_chr
            self._updated_chromosomes.add(chr)

    def get_bounding_region_info(self, region):
        self._update_contents_if_necessary(region.chr)

        if region.chr in self._contents:
            br_info_holder = self._contents[region.chr]

            #Temporary, to store old preprocessed boundingRegion.shelve files
            is_dict = isinstance(br_info_holder, dict)
            if is_dict:
                br_starts = br_info_holder.keys()
            else:
                br_starts = br_info_holder.brStarts

            #idx = self._contents[region.chr].keys().bisect_right(region.start)
            idx = bisect_right(br_starts, region.start)

            if idx > 0:
                if is_dict:
                    br_info = br_info_holder[br_starts[idx-1]]
                else:
                    br_info = br_info_holder.brInfos[idx-1]

                if region.start < br_info.end and region.end <= br_info.end:
                    return br_info

            if not self._minimal_region == region:
                #
                #There are bounding regions in the same chromosome, but not any encompassing the user bin
                #Thus the bounding regions are explicitly defined (not just the complete chromosome)
                #
                from gtrackcore.util.CommonFunctions import prettyPrintTrackName
                raise OutsideBoundingRegionError("The analysis region '%s' is outside the bounding regions of track: %s" \
                                                 % (region, prettyPrintTrackName(self._track_name)))

        return BoundingRegionInfo(region.start, region.end, 0, 0, 0, 0)


    def _get_total_element_count_for_chr(self, chr):
        self._update_contents_if_necessary(chr)

        if chr in self._contents:
            #Temporary
            br_info_holder = self._contents[chr]
            if isinstance(br_info_holder, dict):
                br_infos_for_chr = br_info_holder.values()
            else:
                br_infos_for_chr = br_info_holder.brInfos
            return br_infos_for_chr[-1].endIdx - br_infos_for_chr[0].startIdx
        else:
            return 0

    def get_total_element_count(self):
        return sum(self._get_total_element_count_for_chr(chr) for chr in GenomeInfo.getExtendedChrList(self._genome))

    def get_all_bounding_regions_for_chr(self, chr):
        self._update_contents_if_necessary(chr)

        if chr in self._contents:
            #Temporary
            brInfoHolder = self._contents[chr]
            if isinstance(brInfoHolder, dict):
                brInfosForChr = brInfoHolder.values()
            else:
                brInfosForChr = brInfoHolder.brInfos
            for brInfo in brInfosForChr:
                yield GenomeRegion(self._genome, chr, brInfo.start, brInfo.end)

    def get_all_bounding_regions(self):
        if not self.file_exists():
            from gtrackcore.util.CommonFunctions import prettyPrintTrackName
            raise BoundingRegionsNotAvailableError('Bounding regions not available for track: ' + \
                                                   prettyPrintTrackName(self._track_name))

        for chr in GenomeInfo.getExtendedChrList(self._genome):
            for reg in self.get_all_bounding_regions_for_chr(chr):
                yield reg