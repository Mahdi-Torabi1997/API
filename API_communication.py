import struct
import requests
import pandas as pd
from datetime import datetime

# Constants
CLIENT_ID = ""
CLIENT_SECRET = ""


################# util funcs ###################
def parseStringInt32(stringData, startIndex):
    b = stringData[startIndex: startIndex + 4]
    return int.from_bytes(b, byteorder="little")


def parseStringInt16(stringData, startIndex):
    b = stringData[startIndex: startIndex + 2]
    return int.from_bytes(b, byteorder="little")


def parseStringFloat(stringData, startIndex):
    b = stringData[startIndex: startIndex + 4]
    return struct.unpack("f", b)[0]


###############################################

class SkeletonModel(object):
    def __init__(self, tracker_id, person_id, XCoords, YCoords):
        self.TrackerId = tracker_id
        self.PersonId = person_id
        self.XCoords = XCoords
        self.YCoords = YCoords


class Frame(object):
    def __init__(self, camera_id, people, timestamp):
        self.cameraId = camera_id
        self.skeletons = people
        self.timestamp = timestamp


class RecordParser(object):
    def __init__(self, client_id=CLIENT_ID, client_secret=CLIENT_SECRET):
        self.client_id = client_id
        self.client_secret = client_secret
        self.get_token()
        self.binary_datas = []
        self.recordid_pairs = []
        self.records = []
        keypoint_names = ["keypoint{}".format(i) for i in range(18)]
        self.df = pd.DataFrame(columns=(["time", "camera_id", "person_id"] + keypoint_names))

    # request access token
    def get_token(self):
        url = "https://canada-1.oauth.altumview.com/v1.0/token"
        token_data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
            "scope": "camera:write camera:read",
        }
        self.token = requests.api.post(url, data=token_data).json()["access_token"]

    def _add_records(self, requested_records):
        records = []
        for pair in requested_records:
            camera_id = pair["camera_id"]
            record_ids = pair["record_ids"]
            # print(len(record_ids))
            for record_id in record_ids:
                records.append([camera_id, record_id])
        self.recordid_pairs = self.recordid_pairs + records

    # get record_ids and add to self.recordid_pairs:
    # time format example: "01/20/2020 23:12:30"
    def get_records(self, start_time, end_time, camera_id=None):
        start_dt = datetime.strptime(start_time, "%m/%d/%Y %H:%M:%S")
        end_dt = datetime.strptime(end_time, "%m/%d/%Y %H:%M:%S")
        start = int(datetime.timestamp(start_dt))
        end = int(datetime.timestamp(end_dt))
        last_reference_id = -1
        url = "https://api.altumview.ca/v1.0/recordings"
        headers = {"Authorization": f"Bearer {self.token}"}
        body = {
            "start_date": start,
            "end_date": end,
            "page_length": 200,  # max page length possible
            "last_reference_id": last_reference_id
        }
        if camera_id != None:
            body["camera_ids"] = camera_id
        resp = requests.api.get(url, headers=headers, params=body).json()["data"]
        self._add_records(resp["records"])
        has_next = resp["has_next_page"]
        while has_next == True:
            body["last_reference_id"] = resp["last_reference_id"]
            resp = requests.api.get(url, headers=headers, params=body).json()["data"]
            has_next = resp["has_next_page"]
            self._add_records(resp["records"])

    # fetch single record by record id and camera id
    def fetch_recording(self, record_id, camera_id, person_ids=None):
        headers = {"Authorization": f"Bearer {self.token}"}
        url = "https://api.altumview.ca/v1.0/recordings/{}/{}".format(camera_id, record_id)
        response = requests.get(url, headers=headers)
        assert response.status_code == 200, \
            "Failed to fetch recording {} for camera {}, status code: {}, \
                Reason: {}".format(record_id, camera_id, response.status_code, response.reason)
        binary_data = response.content
        # self.binary_datas.append(binary_data)
        self.parse_binary(binary_data, person_ids)

    # fetch all records in self.recordid_pairs and stores in self.binary_datas
    # if provided with camera id, can fetch all records under corresponding camera_id list
    def fetch_all(self, camera_ids=None, person_ids=None):
        # Fetch the recording
        recordid_pairs = []
        if camera_ids != None:
            for record in self.recordid_pairs:
                if record[0] in camera_ids:
                    recordid_pairs.append(record)
        else:
            recordid_pairs = self.recordid_pairs
        for record in recordid_pairs:
            camera_ids, record_id = record
            self.fetch_recording(record_id, camera_ids, person_ids)
            self.recordid_pairs.remove(record)

    # parse all binary data in self.binary_datas
    # store in self.records
    def parse_binary(self, byteList, person_ids=None):
        cameraId = parseStringInt32(byteList, 8)
        timestamp = parseStringInt32(byteList, 12) * 1000
        frameNum = parseStringInt32(byteList, 16)
        frames = []
        pos = 20  # frame data begins
        for _ in range(frameNum):
            delta_time = parseStringInt16(byteList, pos)
            numPeople = parseStringInt16(byteList, pos + 2)
            pos = pos + 4  # people data begins
            people = []
            for _ in range(numPeople):
                personId = parseStringInt32(byteList, pos + 0)
                trackerId = byteList[pos + 4]
                numPoints = byteList[pos + 5]
                pos = pos + 16  # key point data begins
                xs = [0 for _ in range(18)]
                ys = [0 for _ in range(18)]
                for _ in range(numPoints):
                    pt_index = (byteList[pos + 0]) & int(0b00001111)
                    xs[pt_index] = parseStringInt16(byteList, pos + 2) / 65536
                    ys[pt_index] = parseStringInt16(byteList, pos + 4) / 65536
                    pos = pos + 6
                if (person_ids == None) or (personId in person_ids):
                    skeleton = SkeletonModel(trackerId, personId, xs, ys)
                    people.append(skeleton)
            timestamp = delta_time + timestamp  # update current timestamp (in milliseconds)
            frames.append(Frame(cameraId, people, timestamp))
        self.records.append(frames)

    # convert all data stored in self.records to csv file
    # mode: "w", truncate the file first, defualt
    #       "x", exclusive creation, failing if the file already exists
    #       "a", append to the end of the file
    def to_csv(self, filename, mode="w"):
        keypoint_names = ["keypoint{}".format(i) for i in range(18)]
        df = pd.DataFrame(columns=(["time", "camera_id", "person_id"] + keypoint_names))
        d = {}
        i = 0
        for frames in self.records:
            for frame in frames:
                timestamp = frame.timestamp
                camera_id = frame.cameraId
                people = frame.skeletons
                for person in people:
                    person_id = person.PersonId
                    xs = person.XCoords
                    ys = person.YCoords
                    new_df_row = {"time": timestamp, "camera_id": camera_id, "person_id": person_id}
                    for k in range(18):
                        new_df_row["keypoint{}".format(k)] = (xs[k], ys[k])
                    d[i] = new_df_row
                    i = i + 1
        df = pd.DataFrame.from_dict(d, "index")
        df = df.sort_values(by="time", ascending=True)
        # when multiple camera is recording the same person at the same time,
        # only keep the first one
        df = df.drop_duplicates(subset=["time", "person_id"], keep='first')
        df.to_csv(filename, index=False, mode=mode)
        self.records = []


if __name__ == '__main__':
    # initiate a parser
    parser = RecordParser()
    # get all record ids happen between start date and end date
    start_date = "02/05/2024 16:19:0"
    end_date = "02/05/2024 21:0:0"
    parser.get_records(start_date, end_date)

    # fetch all records
    # print(datetime.now())
    parser.fetch_all(camera_ids=[4924])
    # fetach individual recordings by camera id and record id
    # parser.fetch_recording(camera_id=room1, record_id=record1)

    # convert all fetched data into csv file
    # print(datetime.now())
    parser.to_csv("tmp_Front_above.csv")

    # print(datetime.now())