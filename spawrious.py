import os
import tarfile
import urllib
import urllib.request

import torch
from torch.utils.data import ConcatDataset, Subset, TensorDataset
from torchvision import transforms
from torchvision.datasets import MNIST, ImageFolder
from tqdm import tqdm
from config_spawrious import get_config


def _extract_dataset_from_tar(
    tar_file_name: str, data_dir: str, remove_tar_after_extracting: bool = True
) -> None:
    tar_file_dst = os.path.join(data_dir, tar_file_name)
    print("Extracting dataset...")
    tar = tarfile.open(tar_file_dst, "r:gz")
    tar.extractall(os.path.dirname(tar_file_dst))
    tar.close()
    print("Dataset extracted. Delete tar file.")
    if remove_tar_after_extracting:
        os.remove(tar_file_dst)


def _download_dataset_if_not_available(
    dataset_name: str, data_dir: str, remove_tar_after_extracting: bool = True
) -> None:
    """
    datasets.txt file, which is present in the data_dir, is used to check if the dataset is already extracted. If the dataset is already extracted, then the tar file is not downloaded again. 
    """
    
    dataset_name = dataset_name.lower()
    if dataset_name.split('_')[0] == 'm2m':
        dataset_name = 'm2m'

    url_dict = {
        "entire_dataset": "https://www.dropbox.com/s/wc9mwza5yk66i83/spawrious224.tar.gz?dl=1",
        "o2o_easy": "https://www.dropbox.com/s/bonf1elisg2ohiq/spawrious__o2o_easy.tar.gz?dl=1",
        "o2o_medium": "https://www.dropbox.com/s/xfea065mhh70me1/spawrious__o2o_medium.tar.gz?dl=1",
        "o2o_hard": "https://www.dropbox.com/s/m5eeqp0nsc31nyt/spawrious__o2o_hard.tar.gz?dl=1",
        "m2m": "https://www.dropbox.com/s/spwszi0rxbf53f8/spawrious__m2m.tar.gz?dl=1",
    }
    tar_file_name = f"spawrious__{dataset_name}.tar.gz"
    tar_file_dst = os.path.join(data_dir, tar_file_name)
    url = url_dict[dataset_name]

    # Check if the tar file is already downloaded and present in the data_dir
    if os.path.exists(tar_file_dst):
        print("Dataset already downloaded.")

        # Check if the datasets.txt file is present, and if the dataset is already extracted
        if os.path.exists(os.path.join(data_dir, "datasets.txt")):
            with open(os.path.join(data_dir, 'datasets.txt'), 'r') as f:
                lines = set(f.readlines())
                if (dataset_name in lines) or ('entire_dataset' in lines):
                    print("... and extracted.")
                else:
                    print("Dataset not extracted. Extracting...")
                    _extract_dataset_from_tar(tar_file_name, data_dir, remove_tar_after_extracting)

                    # Write the dataset name to the datasets.txt file to mark extraction
                    with open(os.path.join(data_dir, 'datasets.txt'), 'a') as f:
                        f.write('\n' + dataset_name)

        # If the datasets.txt file is not present, then extract the dataset
        else:
            print("Dataset not extracted. Extracting...")
            _extract_dataset_from_tar(tar_file_name, data_dir, remove_tar_after_extracting)

            # Write the dataset name to the datasets.txt file to mark extraction
            with open(os.path.join(data_dir, 'datasets.txt'), 'a') as f:
                f.write('\n' + dataset_name)

    # Check if the dataset is already extracted by inspecting the datasets.txt file
    else:
        download = True

        # Check if the datasets.txt file is present, and if the dataset is already extracted
        if os.path.exists(os.path.join(data_dir, "datasets.txt")):
            with open(os.path.join(data_dir, 'datasets.txt'), 'r') as f:
                lines = set(f.readlines())
                if (dataset_name in lines) or ('entire_dataset' in lines):
                    print("Dataset already downloaded and extracted.")
                    download = False

        # Download if the dataset is not already extracted
        if download:
            print("Dataset not found. Downloading...")
            response = urllib.request.urlopen(url)
            total_size = int(response.headers.get("Content-Length", 0))
            block_size = 1024

            # Track progress of download
            progress_bar = tqdm(total=total_size, unit="iB", unit_scale=True)
            with open(tar_file_dst, "wb") as f:
                while True:
                    buffer = response.read(block_size)
                    if not buffer:
                        break
                    f.write(buffer)
                    progress_bar.update(len(buffer))
            progress_bar.close()
            
            print("Dataset downloaded. Extracting...")
            _extract_dataset_from_tar(tar_file_name, data_dir, remove_tar_after_extracting)

            # Write the dataset name to the datasets.txt file to mark extraction
            with open(os.path.join(data_dir, 'datasets.txt'), 'a') as f:
                f.write('\n' + dataset_name)


class MultipleDomainDataset:
    N_STEPS = 5001  # Default, subclasses may override
    CHECKPOINT_FREQ = 100  # Default, subclasses may override
    N_WORKERS = 8  # Default, subclasses may override
    ENVIRONMENTS = None  # Subclasses should override
    INPUT_SHAPE = None  # Subclasses should override

    def __getitem__(self, index):
        return self.datasets[index]

    def __len__(self):
        return len(self.datasets)


## Spawrious base class
class SpawriousBenchmark(MultipleDomainDataset):
    ENVIRONMENTS = ["Test", "SC_group_1", "SC_group_2"]

    def __init__(
        self, train_combinations, test_combinations, root_dir, augment=True, type1=False
    ):
        self.input_shape = (3, 224, 224)
        self.num_classes = 4

        self.type1 = type1

        train_data_list = []
        test_data_list = []

        self.class_list = ["bulldog", "corgi", "dachshund", "labrador"]

        test_transforms_list = [
            transforms.Resize((self.input_shape[1], self.input_shape[2])),
            transforms.transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]

        train_transforms_list = [
            transforms.Resize((self.input_shape[1], self.input_shape[2])),
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(0.3, 0.3, 0.3, 0.3),
            transforms.RandomGrayscale(),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]

        # Build test and validation transforms
        test_transforms = transforms.transforms.Compose(test_transforms_list)

        # Build training data transforms
        if augment:
            train_transforms = transforms.transforms.Compose(train_transforms_list)
        else:
            train_transforms = test_transforms

        # Make train_data_list
        if isinstance(train_combinations, dict):
            for_each_class_group = []
            cg_index = 0
            for classes, comb_list in train_combinations.items():
                for_each_class_group.append([])
                for ind, (location, limit) in enumerate(comb_list):

                    path = os.path.join(root_dir, f"{0}/{location}/")
                    if self.type1:
                        path = os.path.join(root_dir, f"{ind}/{location}/")
                    data = ImageFolder(root=path, transform=train_transforms)

                    classes_idx = [data.class_to_idx[c] for c in classes]
                    to_keep_idx = []
                    for class_to_limit in classes_idx:
                        count_limit = 0
                        for i in range(len(data)):
                            if data[i][1] == class_to_limit:
                                to_keep_idx.append(i)
                                count_limit += 1
                            if count_limit >= limit:
                                break

                    subset = Subset(data, to_keep_idx)

                    for_each_class_group[cg_index].append(subset)
                cg_index += 1
            for group in range(len(for_each_class_group[0])):
                train_data_list.append(
                    ConcatDataset(
                        [
                            for_each_class_group[k][group]
                            for k in range(len(for_each_class_group))
                        ]
                    )
                )
        else:
            for location in train_combinations:

                path = os.path.join(root_dir, f"{0}/{location}/")
                data = ImageFolder(root=path, transform=train_transforms)

                train_data_list.append(data)

        # Make test_data_list
        if isinstance(test_combinations, dict):
            for_each_class_group = []
            cg_index = 0
            for classes, comb_list in test_combinations.items():
                for_each_class_group.append([])
                for ind, location in enumerate(comb_list):

                    path = os.path.join(root_dir, f"{0}/{location}/")
                    if self.type1:
                        path = os.path.join(root_dir, f"{ind}/{location}/")
                    data = ImageFolder(root=path, transform=test_transforms)

                    classes_idx = [data.class_to_idx[c] for c in classes]
                    to_keep_idx = [
                        i for i in range(len(data)) if data.imgs[i][1] in classes_idx
                    ]

                    subset = Subset(data, to_keep_idx)

                    for_each_class_group[cg_index].append(subset)
                cg_index += 1
            for group in range(len(for_each_class_group[0])):
                test_data_list.append(
                    ConcatDataset(
                        [
                            for_each_class_group[k][group]
                            for k in range(len(for_each_class_group))
                        ]
                    )
                )
        else:
            for ind, location in enumerate(test_combinations):

                path = os.path.join(root_dir, f"{0}/{location}/")
                if self.type1:
                    path = os.path.join(root_dir, f"{ind}/{location}/")
                data = ImageFolder(root=path, transform=test_transforms)

                test_data_list.append(data)

        # Concatenate test datasets
        test_data = ConcatDataset(test_data_list)

        self.datasets = [test_data] + train_data_list

    def prepend_path(self, to_prepend):
        ## loop through the datasets concats and subsets to find each ImageFolder type dataset and prepend its root
        for one in self.datasets[0].datasets + self.datasets[1:]:
            for two in one.datasets:
                two.dataset.root = os.path.join(
                    to_prepend, two.dataset.root.replace("./data/", "")
                )
                for idx in range(
                    len(two.dataset.samples)
                ):  ## loop trough each sample and edit its path
                    two.dataset.samples[idx] = (
                        os.path.join(
                            to_prepend,
                            two.dataset.samples[idx][0].replace("./data/", ""),
                        ),
                        two.dataset.samples[idx][1],
                    )

    def build_type1_combination(self, group, test, filler):
        total = 3168
        counts = [int(0.97 * total), int(0.87 * total)]
        combinations = {}
        combinations["train_combinations"] = {
            ## correlated class
            ("bulldog",): [(group[0], counts[0]), (group[0], counts[1])],
            ("dachshund",): [(group[1], counts[0]), (group[1], counts[1])],
            ("labrador",): [(group[2], counts[0]), (group[2], counts[1])],
            ("corgi",): [(group[3], counts[0]), (group[3], counts[1])],
            ## filler
            ("bulldog", "dachshund", "labrador", "corgi"): [
                (filler, total - counts[0]),
                (filler, total - counts[1]),
            ],
        }
        ## TEST
        combinations["test_combinations"] = {
            ("bulldog",): [test[0], test[0]],
            ("dachshund",): [test[1], test[1]],
            ("labrador",): [test[2], test[2]],
            ("corgi",): [test[3], test[3]],
        }
        return combinations

    def build_type2_combination(self, group, test):
        total = 3168
        counts = [total, total]
        combinations = {}
        combinations["train_combinations"] = {
            ## correlated class
            ("bulldog",): [(group[0], counts[0]), (group[1], counts[1])],
            ("dachshund",): [(group[1], counts[0]), (group[0], counts[1])],
            ("labrador",): [(group[2], counts[0]), (group[3], counts[1])],
            ("corgi",): [(group[3], counts[0]), (group[2], counts[1])],
        }
        combinations["test_combinations"] = {
            ("bulldog",): [test[0], test[1]],
            ("dachshund",): [test[1], test[0]],
            ("labrador",): [test[2], test[3]],
            ("corgi",): [test[3], test[2]],
        }
        return combinations

# TODO: clean up these functions

## Spawrious classes for each Spawrious dataset
class SpuriousLocationType1_1(SpawriousBenchmark):
    def __init__(self, root_dir, test_envs, hparams):
        group = ["desert", "jungle", "dirt", "snow"]
        test = ["dirt", "snow", "desert", "jungle"]
        filler = "beach"
        combinations = self.build_type1_combination(group, test, filler)
        super().__init__(
            combinations["train_combinations"],
            combinations["test_combinations"],
            root_dir,
            hparams["data_augmentation"],
            type1=True,
        )


class SpuriousLocationType1_2(SpawriousBenchmark):
    ENVIRONMENTS = ["Test", "SC_group_1", "SC_group_2"]

    def __init__(self, root_dir, test_envs, hparams):
        group = ["mountain", "beach", "dirt", "jungle"]
        test = ["jungle", "dirt", "beach", "snow"]
        filler = "desert"
        combinations = self.build_type1_combination(group, test, filler)
        super().__init__(
            combinations["train_combinations"],
            combinations["test_combinations"],
            root_dir,
            hparams["data_augmentation"],
            type1=True,
        )


class SpuriousLocationType1_3(SpawriousBenchmark):
    ENVIRONMENTS = ["Test", "SC_group_1", "SC_group_2"]

    def __init__(self, root_dir, test_envs, hparams):
        group = ["jungle", "mountain", "snow", "desert"]
        test = ["mountain", "snow", "desert", "jungle"]
        filler = "beach"
        combinations = self.build_type1_combination(group, test, filler)
        super().__init__(
            combinations["train_combinations"],
            combinations["test_combinations"],
            root_dir,
            hparams["data_augmentation"],
            type1=True,
        )


class SpuriousLocationType2_1(SpawriousBenchmark):
    ENVIRONMENTS = ["Test", "SC_group_1", "SC_group_2"]

    def __init__(self, root_dir, test_envs, hparams):
        group = ["dirt", "jungle", "snow", "beach"]
        test = ["snow", "beach", "dirt", "jungle"]
        combinations = self.build_type2_combination(group, test)
        super().__init__(
            combinations["train_combinations"],
            combinations["test_combinations"],
            root_dir,
            hparams["data_augmentation"],
        )


class SpuriousLocationType2_2(SpawriousBenchmark):
    ENVIRONMENTS = ["Test", "SC_group_1", "SC_group_2"]

    def __init__(self, root_dir, test_envs, hparams):
        group = ["desert", "mountain", "dirt", "jungle"]
        test = ["dirt", "jungle", "mountain", "desert"]
        combinations = self.build_type2_combination(group, test)
        super().__init__(
            combinations["train_combinations"],
            combinations["test_combinations"],
            root_dir,
            hparams["data_augmentation"],
        )


class SpuriousLocationType2_3(SpawriousBenchmark):
    ENVIRONMENTS = ["Test", "SC_group_1", "SC_group_2"]

    def __init__(self, root_dir, test_envs, hparams):
        group = ["beach", "snow", "mountain", "desert"]
        test = ["desert", "mountain", "beach", "snow"]
        combinations = self.build_type2_combination(group, test)
        super().__init__(
            combinations["train_combinations"],
            combinations["test_combinations"],
            root_dir,
            hparams["data_augmentation"],
        )

# TODO: create a function to load entire dataset separately

def download_spawrious_dataset(dataset_name: str, root_dir: str):
    """
    Downloads the dataset if it is not already available.
    """
    assert dataset_name.lower() in set(['o2o_easy', 'o2o_medium', 'o2o_hard', 'm2m_easy', 'm2m_medium', 'm2m_hard', 'm2m', 'entire_dataset',])
    os.makedirs(root_dir, exist_ok=True)
    _download_dataset_if_not_available(dataset_name, root_dir)

def get_torch_dataset(dataset_name: str, root_dir: str):
    """
    Returns the dataset as a torch dataset, and downloads it if it is not already available.
    """
    download_spawrious_dataset(dataset_name, root_dir)
    filename_map = {
        "o2o_easy": "sc11.pth",
        "o2o_medium": "sc12.pth",
        "o2o_hard": "sc13.pth",
        "m2m_easy": "sc22.pth",
        "m2m_medium": "sc23.pth",
        "m2m_hard": "sc21.pth",
    }
    filename = filename_map.get(dataset_name.lower())
    if filename is None:
        raise ValueError(f"Invalid dataset type: {dataset_name}")
    path_to_dataset = os.path.join(root_dir, "spawrious224", filename)
    dataset = torch.load(path_to_dataset)
    dataset.prepend_path(root_dir)
    return dataset


if __name__ == "__main__":
    config = get_config()
    download_spawrious_dataset(dataset_name=config.dataset_name, root_dir=config.root_dir)

    # TODO: more stuff here
