
"""
Descending Order using selection sort
"""
class Solution(object):
    def sortArray(self, nums):
        for i in range(0,len(nums)):
            max_index=i
            for j in range (i+1,len(nums)):
                if nums[j] > nums[max_index]:
                    max_index=j
            nums[i],nums[max_index]=nums[max_index],nums[i]
        return nums

"""
ascending order using selection sort
"""
class Solution(object):
    def sortArray(self, nums):
        for i in range(0,len(nums)):
            max_index=i
            for j in range (i+1,len(nums)):
                if nums[j] < nums[max_index]:
                    max_index=j
            nums[i],nums[max_index]=nums[max_index],nums[i]
        return nums
        