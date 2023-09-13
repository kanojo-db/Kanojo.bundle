KANOJO_BASE_URL = 'https://api.kanojodb.com%s'

# Movies
KANOJO_MOVIE_SEARCH = '/search/movie?query=%s'
KANOJO_MOVIE = '/movie/%s'

ARTWORK_ITEM_LIMIT = 15
# How much weight to give ratings vs. vote counts when picking best posters. 0 means use only ratings.
POSTER_SCORE_RATIO = .3
BACKDROP_SCORE_RATIO = .3
STILLS_SCORE_RATIO = .3

####################################################################################################


def Start():

    pass


####################################################################################################


def GetKanojoJSON(url, cache_time=CACHE_1HOUR):
  kanojo_dict = None

  try:
    kanojo_dict = JSON.ObjectFromURL(KANOJO_BASE_URL % url, sleep=2.0, headers={'Accept': 'application/json', 'Authorization': 'Bearer {}'.format(Prefs['token'])}, cacheTime=cache_time)
  except Exception as e:
    Log('Error fetching JSON from Kanojo: %s' % (KANOJO_BASE_URL % url))
    Log(e)

  return kanojo_dict


####################################################################################################


def AppendSearchResult(results, id, name=None, year=-1, score=0, lang=None):

    new_result = dict(id=str(id), name=name, year=int(year),
                      score=score, lang=lang)

    if isinstance(results, list):

        results.append(new_result)

    else:

        results.Append(MetadataSearchResult(**new_result))

####################################################################################################


def DictToMovieMetadataObj(metadata_dict, metadata):

    try:
        if not metadata or not metadata.attrs:
            return
    except AttributeError:
        # TODO: add a more official log message about version number when available
        Log('WARNING: Framework not new enough to use One True Agent')
        return

    for attr_name, attr_obj in metadata.attrs.iteritems():

        if attr_name not in metadata_dict:
            continue

        dict_value = metadata_dict[attr_name]

        if isinstance(dict_value, list):

            attr_obj.clear()
            for val in dict_value:
                attr_obj.add(val)

        elif isinstance(dict_value, dict):

            # Can't access MapObject, so have to write these out
            if attr_name in ['posters', 'art', 'themes']:

                for k, v in dict_value.iteritems():
                    if isinstance(v, tuple):
                        try:
                            attr_obj[k] = Proxy.Preview(
                                HTTP.Request(v[0]).content, sort_order=v[1])
                        except:
                            pass
                    else:
                        attr_obj[k] = v

                attr_obj.validate_keys(dict_value.keys())

            else:
                for k, v in dict_value.iteritems():
                    attr_obj[k] = v

        elif attr_name is 'originally_available_at':

            try:
                attr_obj.setcontent(Datetime.ParseDate(dict_value).date())
            except:
                pass

        else:
            attr_obj.setcontent(dict_value)

    # The following are special kind of objects
    if 'roles' in metadata_dict:
        metadata.roles.clear()
        for role in metadata_dict['roles']:
            meta_role = metadata.roles.new()
            if 'role' in role:
                meta_role.role = role['role']
            if 'name' in role:
                meta_role.name = role['name']
            if 'photo' in role:
                meta_role.photo = role['photo']


####################################################################################################
def PerformKanojoMovieSearch(results, media, lang):
        # Replace spaces in the title (a product code) with dashes, since Plex's scanner removes them
        kanojo_dict = GetKanojoJSON(url=KANOJO_MOVIE_SEARCH % (
            media.name.replace(' ', '-')))

        if isinstance(kanojo_dict, dict) and 'data' in kanojo_dict:
            for _, movie in enumerate(kanojo_dict['data']):
                score = 100
                # Multiply the Levenshtein Distance by 10 to account for how short product codes are.
                score = score - \
                    abs(String.LevenshteinDistance(
                        movie['product_code'].lower(), media.name.replace(' ', '-').lower())) * 50

                if 'release_date' in movie and movie['release_date']:
                    release_year = int(movie['release_date'].split('-')[0])
                else:
                    release_year = -1

                if media.year and int(media.year) > 1900 and release_year:
                    year_diff = abs(int(media.year) - release_year)

                    if year_diff <= 1:
                        score = score + 10
                    else:
                        score = score - (5 * year_diff)

                Log('Score: %d' % score)
                if score <= 0:
                    continue
                else:
                    id = movie['product_code']

                    AppendSearchResult(results=results,
                                        id=id,
                                        name="[{0}] {1}".format(movie['product_code'], movie['original_title']),
                                        year=release_year,
                                        score=score,
                                        lang=lang)

####################################################################################################


def PerformKanojoMovieUpdate(metadata_id, lang, existing_metadata):

    metadata = dict(id=metadata_id)

    kanojo_dict = GetKanojoJSON(url=KANOJO_MOVIE % (metadata_id))

    if not isinstance(kanojo_dict, dict):
        return None

    # Rating.
    votes = kanojo_dict.get('vote_count') or 0
    rating = kanojo_dict.get('vote_average') or 0.0
    if votes > 3:
        metadata['rating'] = rating
        metadata['audience_rating'] = 0.0
        metadata['rating_image'] = None
        metadata['audience_rating_image'] = None

    # Title of the film.
    metadata['title'] = metadata['title'] = kanojo_dict.get('title')

    if 'original_title' in kanojo_dict and kanojo_dict['original_title'] != metadata['title']:
        metadata['original_title'] = kanojo_dict['original_title']

    # Release date.
    try:
        metadata['originally_available_at'] = kanojo_dict['release_date']
        metadata['year'] = Datetime.ParseDate(
            kanojo_dict['release_date']).date().year
    except:
        pass

    # Runtime.
    try:
        metadata['duration'] = int(kanojo_dict['runtime']) * 60 * 1000
    except:
        pass

    # Genres.
    metadata['genres'] = []
    for genre in (kanojo_dict.get('genres') or list()):
        metadata['genres'].append(genre.get('name', '').strip())

    # Collections.
    metadata['collections'] = []
    if Prefs['collections'] and isinstance(kanojo_dict.get('belongs_to_series', None), dict):
        metadata['collections'].append(kanojo_dict['belongs_to_series'])

    # Studio.
    if 'studios' in kanojo_dict and len(kanojo_dict['studios']) > 0:
        try:
            index = kanojo_dict['studios'][0]['id']
        except:
            index = ''  # All numbers are less than an empty string
        company = None

        for studio in kanojo_dict['studios']:
            Log('Studio: %s' % studio)
            if (studio.get('id') or '') <= index:  # All numbers are less than an empty string
                index = studio['id']
                company = studio['name'].strip()

        metadata['studio'] = company

    else:
        metadata['studio'] = None

    # Country.
    metadata['countries'] = ['Japan']

    # Cast.
    metadata['roles'] = list()

    try:
        for member in kanojo_dict.get('cast') or list():
            try:
                role = dict()
                # Since models basically always play themselves, we'll use their age as the role.
                role['role'] = member['age_text']
                role['name'] = member['name']
                if member['profile_path'] is not None:
                    role['photo'] = member['profile_path']
                metadata['roles'].append(role)
            except:
                pass
    except:
        pass

    metadata['posters'] = dict()
    metadata['posters'][kanojo_dict['poster_path']] = Proxy.Media(HTTP.Request(kanojo_dict['poster_path']).content)

    # Backdrops.
    metadata['art'] = dict()
    metadata['art'][kanojo_dict['backdrop_path']] = Proxy.Media(HTTP.Request(kanojo_dict['backdrop_path']).content)

    return metadata

####################################################################################################


class KanojoAgent(Agent.Movies):

    name = 'Kanojo'
    languages = [Locale.Language.Japanese]
    primary_provider = True
    accepts_from = ['com.plexapp.agents.localmedia']

    def search(self, results, media, lang, manual):

        PerformKanojoMovieSearch(results, media, lang)

    def update(self, metadata, media, lang):

        metadata_dict = PerformKanojoMovieUpdate(metadata.id, lang, metadata)

        if metadata_dict is None:
            Log('Kanojo was unable to get any metadata for %s (lang = %s)' %
                (metadata.id, lang))
            return

        DictToMovieMetadataObj(metadata_dict, metadata)

####################################################################################################


class FakeMediaObj():

    def __init__(self, id, name, year):
        self.name = name
        self.year = year
        self.primary_metadata = FakePrimaryMetadataObj(id)

####################################################################################################


class FakePrimaryMetadataObj():

    def __init__(self, id):
        self.id = id
