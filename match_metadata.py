from __future__ import print_function, division
import os
import sys
import argparse
import librosa
import Levenshtein
import numpy as np
import pandas as pd
from pathlib import Path

from match_salami_files import search_for_song, get_info_from_youtube, download_and_report, downloaded_audio_folder

def parse_args():
	parser = argparse.ArgumentParser(description='Search and download music on YouTube based on track metadata.')
	parser.add_argument('input', type=str, help='Input csv file with columns: track_id, title, artist_name, duration')
	parser.add_argument('--max-results', type=int, help="Maximum number of search results to consider.", default=10)
	parser.add_argument('--report-file', type=str, help="csv file of processed files and results. Used to continue previous sessions", default='.match_metadata')
	parser.add_argument('--interactive', action="store_true", help="Select candidates interactively.", default=False)
	parser.add_argument('--duration-similarity-threshold', type=float, help="Duration similarity filter threshold.", default=0.95)
	parser.add_argument('--metadata-similarity-threshold', type=float, help="Metadata similarity filter threshold..", default=0.8)
	args = parser.parse_args()
	return args

def inputNumber(message):
  while True:
    try:
       userInput = int(input(message))
    except ValueError:
       print("Not an integer! Try again.")
       continue
    else:
       return userInput
       break

def duration_similarity(x,y):
	return (x+y)/(np.abs(x-y)+x+y)

def metadata_similarity(x,y):
	distance = Levenshtein.distance(x.lower(), y.lower())
	return 1 - (distance/max(len(x), len(y)))

def postprocess_result(search_responses, query, duration):
	df = pd.DataFrame(columns=['vid', 'rank', 'artist', 'title', 'duration', 'duration_similarity', 'metadata_similarity'])
	for i,item in enumerate(search_responses['items']):
		try:
			vid = item['id']['videoId']
			rank = item['rank']
			more_info = get_info_from_youtube(vid)
			msim = metadata_similarity(query, f'{more_info["artist"]} {more_info["track"]}')
			dsim = duration_similarity(duration, more_info['duration'])
			df.loc[i] = [vid,rank, more_info['artist'], more_info['track'], more_info['duration'], dsim, msim]
		except (KeyboardInterrupt):
			raise
		except:
			print("Video connection failed.")
			df.loc[i] = [vid,rank,'','','',0,0]
	return df

def main(argv):

	args = parse_args()

	tracks = pd.read_csv(args.input)
	report_file_columns = ['track_id', 'title', 'artist', 'vid', 'mp3']
	report_file = pd.DataFrame(columns=report_file_columns)
	if Path(args.report_file).exists():
		report_file = pd.read_csv(args.report_file, header=None)
		report_file.columns = report_file_columns

	for i, row in tracks.iterrows():
		if row['track_id'] in report_file.values:
			print(f'Skipping track {row["track_id"]}')
			continue

		print(f'Searching track #{i}: {row["artist_name"]} / {row["title"]} ({row["duration"]}s)')

		query = f'{row["artist_name"]} {row["title"]}'
		search_responses = search_for_song(query, maxResults=args.max_results)
		df = postprocess_result(search_responses, query, row["duration"])
		if df.empty:
			print(f'No match for track #{i}: {row["artist_name"]} / {row["title"]}')
			report = pd.DataFrame([{'track_id': row['track_id'], 'title':'', 'artist':'', 'vid': 'not found', 'mp3': ''}])
			report.to_csv(args.report_file, mode='a', header=False, index=False)
			continue

		shortlist = pd.DataFrame()
		if args.interactive:
			print(df[['artist', 'title', 'duration', 'duration_similarity', 'metadata_similarity']])
			selection = inputNumber("Select candidate (-1 to skip): ")
			if selection < 0 or selection > len(df):
				continue
			shortlist = df.iloc[[selection]]
		else:
			shortlist = df[(df.duration_similarity > args.duration_similarity_threshold) & (df.metadata_similarity > args.metadata_similarity_threshold)]
			shortlist = shortlist.sort_values(by=['duration_similarity', 'metadata_similarity'], ascending=False)
		if shortlist.empty:
			print(f'Empty shortlist')
			report = pd.DataFrame([{'track_id': row['track_id'], 'title':'', 'artist':'', 'vid': 'not found', 'mp3': 'empty shortlist'}])
			report.to_csv(args.report_file, mode='a', header=False, index=False)
			continue

		vid = shortlist.iloc[0,0]
		result = download_and_report(vid)
		if 'error' in result:
			print(f'Error downloading track #{i}: {row["artist_name"]} / {row["title"]}')
			report = pd.DataFrame([{'track_id': row['track_id'], 'title':'', 'artist':'', 'vid': 'not found', 'mp3': 'error downloading track'}])
			report.to_csv(args.report_file, mode='a', header=False, index=False)
			continue

		mp3 = (Path(downloaded_audio_folder)/Path(vid)).with_suffix('.mp3')
		mp3.rename((Path(downloaded_audio_folder)/Path(row['track_id']).with_suffix('.mp3')))

		report = pd.DataFrame([{'track_id': row['track_id'], 'title':row["title"], 'artist':row["artist_name"], 'vid': vid, 'mp3': mp3.as_posix()}])
		report.to_csv(args.report_file, mode='a', header=False, index=False)

if __name__ == "__main__":
	main(sys.argv)
