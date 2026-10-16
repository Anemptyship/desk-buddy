import cv2
import numpy as np
import pytest

from desk_buddy.color import hlg_to_srgb
from desk_buddy.geometry import fit_plane, project, stabilize_depth, transform, unproject
from desk_buddy.tracking import robust_homography, warp


def test_world_camera_roundtrip_with_rotation_and_translation():
    K = np.array([[431.,0,32],[0,429.,24],[0,0,1.]])
    d = np.linspace(.3, 1.6, 48*64).reshape(48,64)
    camera = unproject(d,K).reshape(-1,3)
    pose = np.eye(4)
    pose[:3,:3] = cv2.Rodrigues(np.array([.17,-.25,.09]))[0]
    pose[:3,3] = [.15,-.2,.07]
    world = transform(camera,np.linalg.inv(pose))
    uv,z = project(world,K,pose)
    y,x = np.indices(d.shape)
    np.testing.assert_allclose(uv,np.c_[x.ravel(),y.ravel()],atol=1e-10)
    np.testing.assert_allclose(z,d.ravel(),atol=1e-10)


def test_ransac_rejects_vertical_wall_and_outliers():
    rng = np.random.default_rng(4)
    desk = np.c_[rng.uniform(-.4,.4,(600,2)), -.014+rng.normal(0,.001,600)]
    wall = np.c_[np.ones(900)*.4,rng.uniform(-.5,.5,(900,2))]
    points = np.r_[desk,wall,rng.uniform(-1,1,(100,3))]
    plane = fit_plane(points,threshold=.004)
    assert np.dot(plane["normal"],[0,0,1]) > .999
    assert abs(plane["offset"]-.014) < .001
    assert plane["inlier_rms_m"] < .002


def test_invalid_depth_is_never_filled_from_history():
    K = np.array([[30.,0,4],[0,30.,3],[0,0,1.]])
    current = np.ones((6,8),np.float32)
    current[2,3] = 0
    rgb = np.ones((6,8,3),np.uint8)*100
    result,count = stabilize_depth(current,np.ones_like(current),K,K,np.eye(4),np.eye(4),rgb,rgb)
    assert result[2,3] == 0
    assert count == 47


def test_moving_foreground_and_color_change_reject_history():
    K = np.array([[30.,0,4],[0,30.,3],[0,0,1.]])
    prev = np.ones((6,8),np.float32)
    current = prev.copy()
    current[2:4,2:4] = .6
    rgb = np.ones((6,8,3),np.uint8)*100
    prev_rgb = rgb.copy()
    prev_rgb[:,5] = 200
    result,count = stabilize_depth(current,prev,K,K,np.eye(4),np.eye(4),rgb,prev_rgb)
    np.testing.assert_allclose(result,current)
    assert count == 48-4-6


def test_pose_reprojection_moves_depth_history_to_new_pixels():
    K = np.array([[30.,0,4],[0,30.,3],[0,0,1.]])
    current = np.ones((6,8),np.float32)*1.01
    previous = np.ones_like(current)
    pose = np.eye(4)
    pose[0,3] = 1/30
    rgb = np.ones((6,8,3),np.uint8)*100
    result,count = stabilize_depth(current,previous,K,K,pose,np.eye(4),rgb,rgb)
    np.testing.assert_allclose(result[:,0],1.01,atol=1e-6)
    np.testing.assert_allclose(result[:,1:],1.0065,atol=1e-6)
    assert count == 42


def test_heldout_homography_with_outliers():
    rng = np.random.default_rng(9)
    src = rng.uniform(0,600,(180,2))
    H = np.array([[1.03,.04,12],[-.02,.95,4],[.0001,-.0002,1.]])
    dst = warp(src,H)+rng.normal(0,.12,src.shape)
    dst[::7] = rng.uniform(0,600,(len(dst[::7]),2))
    actual,_,_,error = robust_homography(src,dst)
    assert np.median(error) < .4
    assert np.median(np.linalg.norm(warp(src,actual)-warp(src,H),axis=1)) < .2


def test_hlg_fixed_transform_is_finite_monotonic_and_neutral():
    gray = np.repeat(np.linspace(0,1,1024)[:,None],3,axis=1)
    output = hlg_to_srgb(gray)
    assert np.all(np.isfinite(output))
    assert np.all(np.diff(output,axis=0) >= -1e-6)
    np.testing.assert_allclose(output[0],0,atol=1e-7)
    np.testing.assert_allclose(output[:,0],output[:,1],atol=3e-6)
    assert .85 < output[-1,0] <= 1
